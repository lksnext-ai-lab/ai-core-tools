// ==================== MARKETPLACE TYPES ====================

/** Predefined marketplace categories (mirrors backend MARKETPLACE_CATEGORIES) */
export const MARKETPLACE_CATEGORIES = [
  "Productivity",
  "Research",
  "Writing",
  "Code",
  "Data Analysis",
  "Customer Support",
  "Education",
  "Other",
] as const;

export type MarketplaceCategory = (typeof MARKETPLACE_CATEGORIES)[number];

/** Agent marketplace visibility levels */
export type MarketplaceVisibility = "unpublished" | "private" | "public";

/** Agent card displayed in the marketplace catalog grid */
export interface MarketplaceAgentCard {
  agent_id: number;
  display_name: string;
  short_description: string | null;
  category: string | null;
  tags: string[] | null;
  icon_url: string | null;
  app_name: string;
  app_id: number;
  has_knowledge_base: boolean;
  published_at: string | null;
}

/** Full agent detail shown on the marketplace agent page */
export interface MarketplaceAgentDetail {
  agent_id: number;
  display_name: string;
  short_description: string | null;
  long_description: string | null;
  category: string | null;
  tags: string[] | null;
  icon_url: string | null;
  cover_image_url: string | null;
  app_name: string;
  app_id: number;
  has_knowledge_base: boolean;
  has_memory: boolean;
  published_at: string | null;
}

/** Paginated catalog response */
export interface MarketplaceCatalogResponse {
  agents: MarketplaceAgentCard[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** Marketplace profile for EDITOR+ management */
export interface MarketplaceProfile {
  id: number;
  agent_id: number;
  display_name: string | null;
  short_description: string | null;
  long_description: string | null;
  category: string | null;
  tags: string[] | null;
  icon_url: string | null;
  cover_image_url: string | null;
  published_at: string | null;
  updated_at: string | null;
}

/** Request body for creating/updating a marketplace profile */
export interface MarketplaceProfileUpdate {
  display_name?: string | null;
  short_description?: string | null;
  long_description?: string | null;
  category?: string | null;
  tags?: string[] | null;
  icon_url?: string | null;
  cover_image_url?: string | null;
}

/** Marketplace conversation item */
export interface MarketplaceConversation {
  conversation_id: number;
  agent_id: number;
  title: string | null;
  created_at: string;
  updated_at: string;
  last_message: string | null;
  message_count: number;
  agent_display_name: string;
  agent_icon_url: string | null;
}

/** Query parameters for browsing the marketplace catalog */
export interface MarketplaceCatalogParams {
  search?: string;
  category?: string;
  my_apps_only?: boolean;
  page?: number;
  page_size?: number;
  sort_by?: "relevance" | "newest" | "alphabetical";
}
