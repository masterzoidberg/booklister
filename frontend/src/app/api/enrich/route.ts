/**
 * Next.js API Route for AI metadata enrichment
 * 
 * This route calls the backend vision extraction endpoint to enrich book metadata
 * and returns structured JSON with all extracted fields.
 * 
 * Server-only route - no client imports allowed.
 */

import { NextRequest, NextResponse } from 'next/server';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

export const runtime = 'nodejs';

export interface EnrichRequest {
  bookId: string;
  imageUrls?: string[];
}

export interface EnrichResponse {
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

/**
 * POST /api/enrich
 * 
 * Enriches book metadata by calling the backend vision extraction endpoint.
 * 
 * Request body:
 *   { bookId: string, imageUrls?: string[] }
 * 
 * Response:
 *   { title, author, isbn13, year, publisher, aiTitle, aiDescription, priceHints }
 */
export async function POST(request: NextRequest) {
  let body: EnrichRequest;
  try {
    body = await request.json();
    
    // Validate payload
    if (!body.bookId) {
      return NextResponse.json(
        { error: 'Missing required field: bookId' },
        { status: 400 }
      );
    }

    console.log('enrich: calling backend vision extraction', { bookId: body.bookId });

    // Call backend vision extraction endpoint
    const visionResponse = await fetch(`${API_BASE_URL}/ai/vision/${body.bookId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!visionResponse.ok) {
      const errorData = await visionResponse.json().catch(() => ({ detail: `Backend error: ${visionResponse.status}` }));
      console.error('enrich error: vision extraction failed', { 
        status: visionResponse.status, 
        error: errorData.detail,
        bookId: body.bookId 
      });
      
      return NextResponse.json(
        { error: errorData.detail || `Vision extraction failed: ${visionResponse.status}` },
        { status: visionResponse.status }
      );
    }

    const visionResult = await visionResponse.json();
    
    // Handle errors in 200 response (non-fatal errors like missing provider)
    if (!visionResult.ok && visionResult.errors && visionResult.errors.length > 0) {
      console.warn('enrich warning: vision extraction returned errors', { 
        errors: visionResult.errors,
        bookId: body.bookId 
      });
      
      // Return 200 with errors payload - UI will show toast
      return NextResponse.json(
        { 
          errors: visionResult.errors,
          data: null,
          message: visionResult.errors.join(', ')
        },
        { status: 200 }
      );
    }

    // Fetch updated book to get all fields including AI-generated fields
    const bookResponse = await fetch(`${API_BASE_URL}/book/${body.bookId}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!bookResponse.ok) {
      console.error('enrich error: failed to fetch updated book', { 
        status: bookResponse.status,
        bookId: body.bookId 
      });
      
      // Still return the mapped fields from vision extraction even if book fetch fails
      const mappedFields = visionResult.mapped_fields || {};
      return NextResponse.json({
        title: mappedFields.title,
        author: mappedFields.author,
        isbn13: mappedFields.isbn13,
        year: mappedFields.year,
        publisher: mappedFields.publisher,
        aiTitle: mappedFields.title_ai,
        aiDescription: mappedFields.description_ai,
        priceHints: {
          min: mappedFields.price_min,
          suggested: mappedFields.price_suggested,
          max: mappedFields.price_max,
        },
      });
    }

    const book = await bookResponse.json();

    // Build enrichment response
    const enrichResult: EnrichResponse = {
      title: book.title,
      author: book.author,
      isbn13: book.isbn13,
      year: book.year,
      publisher: book.publisher,
      aiTitle: book.title_ai,
      aiDescription: book.description_ai,
      priceHints: {
        min: book.price_min,
        suggested: book.price_suggested,
        max: book.price_max,
      },
    };

    console.log('enrich: success', { 
      bookId: body.bookId,
      hasTitle: !!enrichResult.title,
      hasAuthor: !!enrichResult.author,
      hasAiTitle: !!enrichResult.aiTitle,
      hasAiDescription: !!enrichResult.aiDescription,
    });

    return NextResponse.json(enrichResult);

  } catch (error: any) {
    console.error('enrich error: unexpected error', { 
      err: error.message,
      stack: error.stack,
      payload: body || null,
    });

    return NextResponse.json(
      { error: error.message || 'Internal server error during enrichment' },
      { status: 500 }
    );
  }
}

