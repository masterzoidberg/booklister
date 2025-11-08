/**
 * Types for AI enrichment functionality
 */

export interface BookInput {
  bookId: string;
  imageUrls?: string[];
}

export interface EnrichResult {
  title?: string;
  author?: string;
  isbn13?: string;
  year?: string;
  publisher?: string;
  aiTitle?: string;
  aiDescription?: string;
  priceHints?: {
    min?: number;
    suggested?: number;
    max?: number;
  };
}

