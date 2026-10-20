import type { Meta, StoryObj } from '@storybook/react-vite';
import { fn } from 'storybook/test';

import ExpansionDetails from './ExpansionDetails';
import { FormField } from './FormField';

const meta = {
  title: 'UI/ExpansionDetails',
  component: ExpansionDetails,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  decorators: [
    (Story) => (
      <div className="w-[480px] max-w-full">
        <Story />
      </div>
    ),
  ],
  args: {
    header: 'Discovery',
    children: (
      <div className="space-y-1">
        <p className="text-sm font-medium text-fg dark:text-fg-dark">Sitemap URL</p>
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
          https://example.com/sitemap.xml
        </p>
      </div>
    ),
  },
} satisfies Meta<typeof ExpansionDetails>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const WithFormFields: Story = {
  decorators: [
    (Story) => (
      <div className="w-[640px] max-w-full">
        <Story />
      </div>
    ),
  ],
  args: {
    header: 'Discovery',
    children: (
      <>
        <FormField
          id="story_sitemap_url"
          label="Sitemap URL"
          type="url"
          value="https://example.com/sitemap.xml"
          onChange={fn()}
          helpText="Leave empty to skip sitemap discovery."
        />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <FormField
            id="story_seed_url"
            label="Seed URL"
            type="url"
            value="https://example.com/"
            onChange={fn()}
            helpText="Starting URL for link-following crawl."
          />
          <FormField
            id="story_max_depth"
            label="Max depth"
            type="number"
            min={0}
            max={5}
            value={2}
            onChange={fn()}
            helpText="0–5 link-following levels from the seed URL."
          />
        </div>
      </>
    ),
  },
};

export const Stacked: Story = {
  decorators: [
    (Story) => (
      <div className="w-[640px] max-w-full">
        <Story />
      </div>
    ),
  ],
  render: () => (
    <div className="space-y-4">
      <ExpansionDetails header="Discovery">
        <FormField
          id="stacked_sitemap_url"
          label="Sitemap URL"
          type="url"
          value=""
          onChange={fn()}
          placeholder="https://example.com/sitemap.xml"
          helpText="Leave empty to skip sitemap discovery."
        />
      </ExpansionDetails>
      <ExpansionDetails header="Filters">
        <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
          Patterns match against the URL path. Use <code className="rounded bg-tableCab px-1 dark:bg-tableCab-dark">**</code> to
          match any number of path segments (e.g. <code className="rounded bg-tableCab px-1 dark:bg-tableCab-dark">/docs/**</code>).
        </p>
      </ExpansionDetails>
      <ExpansionDetails header="Crawl behaviour">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <FormField
            id="stacked_rate_limit"
            label="Rate limit (requests/second)"
            type="number"
            value={1}
            onChange={fn()}
            helpText="0.1–10 requests per second."
          />
          <FormField
            id="stacked_refresh_interval"
            label="Refresh interval (hours)"
            type="number"
            value={24}
            onChange={fn()}
            helpText="0 = disabled (never auto-crawl)."
          />
        </div>
      </ExpansionDetails>
    </div>
  ),
};
