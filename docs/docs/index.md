---
sidebar_position: 1
slug: /
title: Introduction
---

# Overseer Lite

A lightweight media request system that generates feeds compatible with Sonarr and Radarr. Users can search for TV shows and movies via TMDB and add them to request lists, which are exposed as import list endpoints.

## Features

- **Simple Authentication** - Preshared password with PBKDF2 key derivation and signed session tokens
- **TMDB Integration** - Search movies and TV shows using The Movie Database
- **Sonarr/Radarr Import Lists** - Native JSON formats for direct import
- **Plex Webhook Integration** - Auto-mark requests as added when Plex downloads media
- **Library Sync** - Batch sync Plex library to show "In Library" badges
- **Large Series Warnings** - Visual indicator for TV shows with 7+ seasons
- **PWA Support** - Install as app on iOS/Android
- **Modern UI** - Responsive Svelte frontend with dark mode

## Architecture

Overseer Lite can be deployed in two ways:

### Docker (Self-Hosted)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│    Caddy    │────▶│  Frontend   │
│             │     │  (Reverse   │     │  (Svelte)   │
└─────────────┘     │   Proxy +   │     └─────────────┘
                    │   HTTPS)    │     ┌─────────────┐
                    │             │────▶│   Backend   │
                    └─────────────┘     │  (FastAPI)  │
                                        └──────┬──────┘
                                        ┌──────▼──────┐
                                        │   SQLite    │
                                        └─────────────┘
```

### AWS Serverless

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│ CloudFront  │────▶│  S3 Bucket  │
│             │     │    (CDN)    │     │ (Frontend)  │
└─────────────┘     │             │     └─────────────┘
                    │             │     ┌─────────────┐
                    │             │────▶│   Lambda    │────▶ TMDB API
                    └─────────────┘     │  (FastAPI)  │
                                        └──────┬──────┘
                                        ┌──────▼──────┐
                                        │  DynamoDB   │
                                        └─────────────┘
```

**Estimated AWS Cost: ~$0.50-1/month** (mostly Secrets Manager + Route53)

## Quick Links

- [Docker Deployment](/getting-started/docker) - Get running in minutes with Docker Compose
- [AWS Deployment](/getting-started/aws) - Serverless deployment with Terraform
- [Configuration](/configuration) - Environment variables and settings
- [Plex Integration](/plex-integration) - Webhooks and library sync
- [Sonarr & Radarr](/sonarr-radarr) - Import list setup

## Screenshots

Coming soon!
