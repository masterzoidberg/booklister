const API_BASE_URL = 'http://127.0.0.1:8000';

export interface OAuthStatus {
  connected: boolean;
  expires_at?: number;
  expires_in?: number;
  token_type?: string;
  scope?: string;
  error?: string;
}

export interface AuthUrlResponse {
  auth_url: string;
  redirect_uri: string;
  scopes: string;
}

export interface ExchangeCodeResponse {
  ok: boolean;
  provider: string;
  expires_at: number;
  expires_in: number;
  token_type: string;
  scope?: string;
  created_at: number;
}

export interface SetManualTokenRequest {
  access_token: string;
  expires_in?: number;
  scope?: string;
}

export interface SetManualTokenResponse {
  ok: boolean;
  provider: string;
  expires_at: number;
  expires_in: number;
  token_type: string;
  scope?: string;
  created_at: number;
  message: string;
}

export interface PublishResult {
  success: boolean;
  book_id: string;
  sku?: string;
  offer_id?: string;
  listing_id?: string;
  listing_url?: string;
  steps?: Record<string, any>;
  error?: string;
}

export interface PublishStatus {
  book_id: string;
  sku?: string;
  offer_id?: string;
  listing_id?: string;
  listing_url?: string;
  publish_status?: string;
}

export interface Policy {
  policy_id: string;
  name: string;
  description?: string;
  category_types?: string[];
  marketplace_id?: string;
}

export interface PoliciesResponse {
  payment_policies: Policy[];
  fulfillment_policies: Policy[];
  return_policies: Policy[];
  error?: string;
}

export interface Category {
  category_id: string;
  name: string;
  level: number;
  leaf_category: boolean;
  parent_category_id?: string;
}

export type LeafCategory = {
  category_id: string;
  name: string;
  leaf_category: boolean;
  parent_category_id?: string;
}

export interface CategoriesResponse {
  categories: Category[];
  error?: string;
}

export interface Aspect {
  name: string;
  localized_name?: string;
  required: boolean;
  aspect_mode?: string;
  max_values?: number;
  aspect_data_type?: string;
  recommended_values?: string[];
}

export interface AspectsResponse {
  category_id: string;
  category_tree_id: string;
  aspects: Aspect[];
  error?: string;
}

const api = {
  async get<T>(endpoint: string): Promise<T> {
    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }
      return response.json();
    } catch (error: any) {
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('Backend server is not running. Please ensure the backend is started on http://127.0.0.1:8000');
      }
      throw error;
    }
  },

  async post<T>(endpoint: string, data?: any): Promise<T> {
    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: data ? JSON.stringify(data) : undefined,
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }
      return response.json();
    } catch (error: any) {
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('Backend server is not running. Please ensure the backend is started on http://127.0.0.1:8000');
      }
      throw error;
    }
  },
};

export const ebayOAuthApi = {
  /**
   * Get eBay OAuth authorization URL
   */
  getAuthUrl: async (state?: string): Promise<AuthUrlResponse> => {
    const url = state 
      ? `/ebay/oauth/auth-url?state=${encodeURIComponent(state)}`
      : '/ebay/oauth/auth-url';
    return api.get<AuthUrlResponse>(url);
  },

  /**
   * Exchange authorization code for access token
   */
  exchangeCode: async (code: string): Promise<ExchangeCodeResponse> => {
    return api.post<ExchangeCodeResponse>('/ebay/oauth/exchange', { code });
  },

  /**
   * Set a manual User Token from eBay Developer Console
   */
  setManualToken: async (token: string, expiresIn?: number, scope?: string): Promise<SetManualTokenResponse> => {
    return api.post<SetManualTokenResponse>('/ebay/oauth/set-token', {
      access_token: token,
      expires_in: expiresIn,
      scope: scope
    });
  },

  /**
   * Get current OAuth connection status
   */
  getStatus: async (): Promise<OAuthStatus> => {
    return api.get<OAuthStatus>('/ebay/oauth/status');
  },

  /**
   * Manually refresh access token
   */
  refreshToken: async (): Promise<ExchangeCodeResponse> => {
    return api.post<ExchangeCodeResponse>('/ebay/oauth/refresh');
  },

  /**
   * Disconnect OAuth by deleting stored tokens
   */
  disconnect: async (): Promise<{ ok: boolean; message: string }> => {
    try {
      const response = await fetch(`${API_BASE_URL}/ebay/oauth/disconnect`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `API error: ${response.status}`);
      }
      return response.json();
    } catch (error: any) {
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('Backend server is not running. Please ensure the backend is started on http://127.0.0.1:8000');
      }
      throw error;
    }
  },
};

export const ebayPublishApi = {
  /**
   * Publish book to eBay
   */
  publishBook: async (
    bookId: string,
    options?: {
      payment_policy_id?: string;
      return_policy_id?: string;
      fulfillment_policy_id?: string;
      category_id?: string;
    }
  ): Promise<PublishResult> => {
    return api.post<PublishResult>(`/ebay/publish/${bookId}`, options || {});
  },

  /**
   * Save book as draft (creates offer but doesn't publish)
   */
  saveDraft: async (
    bookId: string,
    options?: {
      payment_policy_id?: string;
      return_policy_id?: string;
      fulfillment_policy_id?: string;
      category_id?: string;
    }
  ): Promise<PublishResult> => {
    return api.post<PublishResult>(`/ebay/publish/${bookId}`, {
      ...(options || {}),
      as_draft: true,
    });
  },

  /**
   * Get publish status for a book
   */
  getPublishStatus: async (bookId: string): Promise<PublishStatus> => {
    return api.get<PublishStatus>(`/ebay/publish/${bookId}/status`);
  },
};

export const ebayPoliciesApi = {
  /**
   * Fetch all payment, fulfillment, and return policies from eBay account
   */
  getPolicies: async (marketplaceId: string = 'EBAY_US'): Promise<PoliciesResponse> => {
    return api.get<PoliciesResponse>(`/ebay/policies?marketplace_id=${encodeURIComponent(marketplaceId)}`);
  },
};

export const ebayCategoriesApi = {
  /**
   * Fetch leaf categories under a parent category (default: Books - 267)
   */
  getLeafCategories: async (parentCategoryId: string = '267', marketplaceId: string = 'EBAY_US'): Promise<CategoriesResponse> => {
    return api.get<CategoriesResponse>(`/ebay/categories/leaf?parent_category_id=${encodeURIComponent(parentCategoryId)}&marketplace_id=${encodeURIComponent(marketplaceId)}`);
  },
  /**
   * Fetch aspects for a specific category
   */
  getCategoryAspects: async (categoryId: string, marketplaceId: string = 'EBAY_US'): Promise<AspectsResponse> => {
    return api.get<AspectsResponse>(`/ebay/categories/${encodeURIComponent(categoryId)}/aspects?marketplace_id=${encodeURIComponent(marketplaceId)}`);
  },
};

/**
 * Fetch leaf categories for AI extraction (simplified interface)
 */
export async function fetchLeafCategories(parentId: string = "267"): Promise<LeafCategory[]> {
  const r = await fetch(`${API_BASE_URL}/ebay/categories/leaf?parent_category_id=${encodeURIComponent(parentId)}`);
  const j = await r.json();
  return j.categories || [];
}

/**
 * Format time until expiration for display
 */
export function formatExpirationTime(expiresIn: number): string {
  if (expiresIn < 60) {
    return `${expiresIn} seconds`;
  } else if (expiresIn < 3600) {
    const minutes = Math.floor(expiresIn / 60);
    return `${minutes} minute${minutes !== 1 ? 's' : ''}`;
  } else {
    const hours = Math.floor(expiresIn / 3600);
    const minutes = Math.floor((expiresIn % 3600) / 60);
    if (minutes === 0) {
      return `${hours} hour${hours !== 1 ? 's' : ''}`;
    }
    return `${hours} hour${hours !== 1 ? 's' : ''} ${minutes} minute${minutes !== 1 ? 's' : ''}`;
  }
}

