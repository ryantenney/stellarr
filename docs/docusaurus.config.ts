import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'Overseer Lite',
  tagline: 'A lightweight media request system for Sonarr and Radarr',
  favicon: 'img/favicon.ico',

  future: {
    v4: true,
  },

  // GitHub Pages URL
  url: 'https://ryantenney.github.io',
  baseUrl: '/overseer-lite/',

  // GitHub Pages deployment config
  organizationName: 'ryantenney',
  projectName: 'overseer-lite',
  trailingSlash: false,

  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'warn',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          routeBasePath: '/', // Docs at root
          editUrl: 'https://github.com/ryantenney/overseer-lite/tree/main/docs/',
        },
        blog: false, // Disable blog
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    colorMode: {
      defaultMode: 'dark',
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Overseer Lite',
      logo: {
        alt: 'Overseer Lite',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Docs',
        },
        {
          href: 'https://github.com/ryantenney/overseer-lite',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Documentation',
          items: [
            { label: 'Getting Started', to: '/' },
            { label: 'Configuration', to: '/configuration' },
            { label: 'API Reference', to: '/api-reference' },
          ],
        },
        {
          title: 'Integrations',
          items: [
            { label: 'Plex Integration', to: '/plex-integration' },
            { label: 'Sonarr & Radarr', to: '/sonarr-radarr' },
          ],
        },
        {
          title: 'More',
          items: [
            {
              label: 'GitHub',
              href: 'https://github.com/ryantenney/overseer-lite',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Overseer Lite. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'json', 'hcl'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
