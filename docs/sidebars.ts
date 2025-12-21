import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'index',
    {
      type: 'category',
      label: 'Getting Started',
      collapsed: false,
      items: [
        'getting-started/docker',
        'getting-started/aws',
      ],
    },
    'configuration',
    {
      type: 'category',
      label: 'Integrations',
      collapsed: false,
      items: [
        'plex-integration',
        'sonarr-radarr',
      ],
    },
    'api-reference',
    'troubleshooting',
  ],
};

export default sidebars;
