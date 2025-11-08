
const API_BASE_URL = 'http://127.0.0.1:8000';

export interface Book {
  id: string;
  status: 'new' | 'auto' | 'needs_review' | 'approved' | 'exported';
  title?: string;
  author?: string;
  publisher?: string;
  year?: string;
  language?: string;
  format?: string;
  edition?: string;
  isbn13?: string;
  ocr_text?: string;
  category_suggestion?: string;
  condition_grade: 'Brand New' | 'Like New' | 'Very Good' | 'Good' | 'Acceptable';
  defects?: string;
  price_suggested?: number;
  price_min?: number;
  price_max?: number;
  quantity: number;
  title_ai?: string;
  description_ai?: string;
  specifics_ai?: Record<string, any>;
  payment_policy_name?: string;
  shipping_policy_name?: string;
  return_policy_name?: string;
  created_at: number;
  updated_at: number;
  images: Image[];
  sku?: string;
  ebay_offer_id?: string;
  ebay_listing_id?: string;
  publish_status?: string;
  ebay_category_id?: string;
  verified?: boolean;
}

export interface Image {
  id: string;
  book_id: string;
  path: string;
  width: number;
  height: number;
  hash: string;
}


const api = {
  async get<T>(endpoint: string): Promise<T> {
    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: `API error: ${response.status}` }));
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
        const errorData = await response.json().catch(() => ({ detail: `API error: ${response.status}` }));
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

  async put<T>(endpoint: string, data?: any): Promise<T> {
    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: data ? JSON.stringify(data) : undefined,
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: `API error: ${response.status}` }));
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

  async uploadImages(files: FileList, folderInfo?: Record<string, string>): Promise<Book[]> {
    try {
      const formData = new FormData();
      Array.from(files).forEach((file) => {
        formData.append('files', file);
      });

      // Add folder information if provided
      if (folderInfo) {
        formData.append('folder_info', JSON.stringify(folderInfo));
      }

      const response = await fetch(`${API_BASE_URL}/ingest/upload`, {
        method: 'POST',
        body: formData,
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const error = new Error(errorData.detail || `Upload error: ${response.status}`);
        (error as any).error = errorData.error || true;
        (error as any).status = response.status;
        throw error;
      }
      
      return response.json();
    } catch (error: any) {
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('Backend server is not running. Please ensure the backend is started on http://127.0.0.1:8000');
      }
      throw error;
    }
  },

  getImageUrl(bookId: string, filename: string): string {
    return `${API_BASE_URL}/images/${bookId}/${filename}`;
  },
};

export const uploadApi = {
  uploadImages: (files: FileList, folderInfo?: Record<string, string>): Promise<Book[]> => 
    api.uploadImages(files, folderInfo),
};

export const booksApi = {
  getQueue: (status?: string): Promise<Book[]> => 
    api.get(`/queue${status ? `?status=${status}` : ''}`),
  
  getBook: (id: string): Promise<Book> => 
    api.get(`/book/${id}`),
  
  updateBook: (id: string, data: Partial<Book>): Promise<Book> => 
    api.put(`/book/${id}`, data),
  
  verifyBook: async (id: string): Promise<Book> =>
    api.put(`/book/${id}`, { verified: true }),
};

export const ebayPublishApi = {
  publishBook: (id: string, options?: {
    payment_policy_id?: string;
    return_policy_id?: string;
    fulfillment_policy_id?: string;
  }): Promise<{
    success: boolean;
    book_id: string;
    sku?: string;
    offer_id?: string;
    listing_id?: string;
    listing_url?: string;
    steps?: Record<string, any>;
    error?: string;
  }> => 
    api.post(`/ebay/publish/${id}`, options || {}),
  
  getPublishStatus: (id: string): Promise<{
    book_id: string;
    sku?: string;
    offer_id?: string;
    listing_id?: string;
    listing_url?: string;
    publish_status?: string;
  }> => 
    api.get(`/ebay/publish/${id}/status`),
};


export interface AISettings {
  provider: 'openai' | 'openrouter' | 'gemini';
  openai_api_key?: string;
  openrouter_api_key?: string;
  gemini_api_key?: string;
  openai_model: string;
  openrouter_model: string;
  gemini_model?: string;
}

export interface UpdateAISettingsRequest {
  provider?: 'openai' | 'openrouter' | 'gemini';
  openai_api_key?: string;
  openrouter_api_key?: string;
  gemini_api_key?: string;
}

export const aiSettingsApi = {
  getSettings: (): Promise<AISettings> => 
    api.get('/ai/settings'),
  
  updateSettings: (data: UpdateAISettingsRequest): Promise<AISettings> => 
    api.post('/ai/settings', data),
  
  testConnection: (): Promise<{
    success: boolean;
    provider: string;
    message: string;
  }> => 
    api.post('/ai/settings/test'),
};


export default api;