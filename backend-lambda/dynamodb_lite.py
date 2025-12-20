"""
Lightweight DynamoDB client using httpx + AWS SigV4.
Replaces boto3 for ~70MB smaller Lambda packages.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

from aws_sigv4 import sign_request


class DynamoDBError(Exception):
    """DynamoDB API error."""
    def __init__(self, error_type: str, message: str):
        self.error_type = error_type
        self.message = message
        super().__init__(f"{error_type}: {message}")


class ConditionalCheckFailedException(DynamoDBError):
    """Raised when a conditional check fails (item already exists, etc)."""
    pass


class DynamoDBClient:
    """Lightweight DynamoDB client."""

    def __init__(self, table_name: str, region: str = None):
        self.table_name = table_name
        self.region = region or os.environ.get('AWS_REGION_NAME', 'us-east-1')
        self.endpoint = f"https://dynamodb.{self.region}.amazonaws.com"
        self._client = None

    def _get_client(self) -> httpx.Client:
        """Lazy-init HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def _request(self, operation: str, payload: dict) -> dict:
        """Make a signed request to DynamoDB."""
        body = json.dumps(payload)

        headers = {
            'Content-Type': 'application/x-amz-json-1.0',
            'X-Amz-Target': f'DynamoDB_20120810.{operation}',
        }

        signed_headers = sign_request(
            method='POST',
            url=self.endpoint,
            headers=headers,
            payload=body,
            service='dynamodb',
            region=self.region,
        )

        response = self._get_client().post(
            self.endpoint,
            headers=signed_headers,
            content=body,
        )

        if response.status_code != 200:
            error = response.json()
            error_type = error.get('__type', 'Unknown').split('#')[-1]
            message = error.get('message', error.get('Message', 'Unknown error'))

            if error_type == 'ConditionalCheckFailedException':
                raise ConditionalCheckFailedException(error_type, message)
            raise DynamoDBError(error_type, message)

        return response.json()

    # --- Type Marshalling ---

    @staticmethod
    def _to_dynamodb(value: Any) -> dict:
        """Convert Python value to DynamoDB type format."""
        if value is None:
            return {'NULL': True}
        elif isinstance(value, bool):
            return {'BOOL': value}
        elif isinstance(value, str):
            return {'S': value}
        elif isinstance(value, (int, float)):
            return {'N': str(value)}
        elif isinstance(value, list):
            return {'L': [DynamoDBClient._to_dynamodb(v) for v in value]}
        elif isinstance(value, dict):
            return {'M': {k: DynamoDBClient._to_dynamodb(v) for k, v in value.items()}}
        else:
            return {'S': str(value)}

    @staticmethod
    def _from_dynamodb(item: dict) -> Any:
        """Convert DynamoDB type format to Python value."""
        if 'S' in item:
            return item['S']
        elif 'N' in item:
            # Try int first, fall back to float
            n = item['N']
            try:
                return int(n)
            except ValueError:
                return float(n)
        elif 'BOOL' in item:
            return item['BOOL']
        elif 'NULL' in item:
            return None
        elif 'L' in item:
            return [DynamoDBClient._from_dynamodb(v) for v in item['L']]
        elif 'M' in item:
            return {k: DynamoDBClient._from_dynamodb(v) for k, v in item['M'].items()}
        else:
            return None

    def _marshal_item(self, item: dict) -> dict:
        """Convert Python dict to DynamoDB Item format."""
        return {k: self._to_dynamodb(v) for k, v in item.items() if v is not None}

    def _unmarshal_item(self, item: dict) -> dict:
        """Convert DynamoDB Item format to Python dict."""
        return {k: self._from_dynamodb(v) for k, v in item.items()}

    def _marshal_key(self, key: dict) -> dict:
        """Marshal a key for DynamoDB."""
        return self._marshal_item(key)

    # --- DynamoDB Operations ---

    def get_item(self, key: dict) -> dict | None:
        """Get an item by key. Returns None if not found."""
        response = self._request('GetItem', {
            'TableName': self.table_name,
            'Key': self._marshal_key(key),
        })

        item = response.get('Item')
        if item:
            return self._unmarshal_item(item)
        return None

    def put_item(self, item: dict, condition_expression: str = None) -> bool:
        """Put an item. Returns True on success."""
        payload = {
            'TableName': self.table_name,
            'Item': self._marshal_item(item),
        }

        if condition_expression:
            payload['ConditionExpression'] = condition_expression

        self._request('PutItem', payload)
        return True

    def delete_item(self, key: dict) -> bool:
        """Delete an item by key."""
        self._request('DeleteItem', {
            'TableName': self.table_name,
            'Key': self._marshal_key(key),
        })
        return True

    def query(
        self,
        key_condition_expression: str,
        expression_attribute_values: dict,
        expression_attribute_names: dict = None,
    ) -> list[dict]:
        """Query items by partition key."""
        payload = {
            'TableName': self.table_name,
            'KeyConditionExpression': key_condition_expression,
            'ExpressionAttributeValues': {
                k: self._to_dynamodb(v) for k, v in expression_attribute_values.items()
            },
        }

        if expression_attribute_names:
            payload['ExpressionAttributeNames'] = expression_attribute_names

        response = self._request('Query', payload)
        items = response.get('Items', [])
        return [self._unmarshal_item(item) for item in items]

    def scan(self, filter_expression: str = None, expression_attribute_values: dict = None) -> list[dict]:
        """Scan the entire table."""
        payload = {'TableName': self.table_name}

        if filter_expression:
            payload['FilterExpression'] = filter_expression
        if expression_attribute_values:
            payload['ExpressionAttributeValues'] = {
                k: self._to_dynamodb(v) for k, v in expression_attribute_values.items()
            }

        # Handle pagination for large tables
        all_items = []
        while True:
            response = self._request('Scan', payload)
            items = response.get('Items', [])
            all_items.extend([self._unmarshal_item(item) for item in items])

            # Check for more pages
            last_key = response.get('LastEvaluatedKey')
            if not last_key:
                break
            payload['ExclusiveStartKey'] = last_key

        return all_items

    def update_item(
        self,
        key: dict,
        update_expression: str,
        expression_attribute_values: dict,
        condition_expression: str = None,
        return_values: str = 'NONE',
    ) -> dict | None:
        """Update an item with an update expression."""
        payload = {
            'TableName': self.table_name,
            'Key': self._marshal_key(key),
            'UpdateExpression': update_expression,
            'ExpressionAttributeValues': {
                k: self._to_dynamodb(v) for k, v in expression_attribute_values.items()
            },
            'ReturnValues': return_values,
        }

        if condition_expression:
            payload['ConditionExpression'] = condition_expression

        response = self._request('UpdateItem', payload)

        if return_values != 'NONE' and 'Attributes' in response:
            return self._unmarshal_item(response['Attributes'])
        return None
