import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://stellarr.dev',
  base: '/docs',
  integrations: [
    starlight({
      title: 'Stellarr',
      logo: {
        src: './src/assets/logo.svg',
      },
      social: {
        github: 'https://github.com/ryantenney/stellarr',
      },
      editLink: {
        baseUrl: 'https://github.com/ryantenney/stellarr/edit/main/docs/',
      },
      customCss: ['./src/styles/custom.css'],
      sidebar: [
        {
          label: 'Getting Started',
          items: [
            { label: 'Introduction', slug: 'index' },
            { label: 'Docker Deployment', slug: 'getting-started/docker' },
            { label: 'AWS Deployment', slug: 'getting-started/aws' },
          ],
        },
        {
          label: 'Guides',
          items: [
            { label: 'Configuration', slug: 'guides/configuration' },
            { label: 'Troubleshooting', slug: 'guides/troubleshooting' },
          ],
        },
        {
          label: 'Integrations',
          items: [
            { label: 'Plex Integration', slug: 'integrations/plex' },
            { label: 'Sonarr & Radarr', slug: 'integrations/sonarr-radarr' },
          ],
        },
        {
          label: 'Architecture',
          items: [
            { label: 'Overview', slug: 'architecture/overview' },
            { label: 'Design Decisions', slug: 'architecture/design-decisions' },
            { label: 'Trending Cache', slug: 'architecture/trending-cache' },
            { label: 'Authentication', slug: 'architecture/authentication' },
          ],
        },
        {
          label: 'Deployment',
          items: [
            { label: 'Deployment Guide', slug: 'deployment/guide' },
            { label: 'Infrastructure Reference', slug: 'deployment/infrastructure' },
            { label: 'CI/CD Pipeline', slug: 'deployment/ci-cd' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'API Reference', slug: 'reference/api' },
          ],
        },
      ],
    }),
  ],
});
