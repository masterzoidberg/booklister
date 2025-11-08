'use client';

import { useState, useEffect, useCallback } from 'react';
import { Book, booksApi, ebayPublishApi } from '@/lib/api';
import { ebayOAuthApi, ebayPublishApi as ebayPublishHelper, ebayPoliciesApi, ebayCategoriesApi, PoliciesResponse, Policy, CategoriesResponse, Category, AspectsResponse, Aspect, fetchLeafCategories, LeafCategory } from '@/lib/ebay';
import { useToast } from '@/hooks/use-toast';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { ImageCarousel } from '@/components/ImageCarousel';
import { ChevronLeft, ChevronRight, Check, SkipForward, RefreshCw, Search, Download, ScanLine, CheckCircle, Upload, ExternalLink, Loader2, CreditCard, Package, ArrowLeftRight, BookOpen, FileCheck } from 'lucide-react';

const API_BASE_URL = 'http://127.0.0.1:8000';

export function ReviewPage() {
  const { toast } = useToast();
  const [books, setBooks] = useState<Book[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [publishLoading, setPublishLoading] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const [oauthConnected, setOAuthConnected] = useState<boolean | null>(null);
  const [policies, setPolicies] = useState<PoliciesResponse | null>(null);
  const [policiesLoading, setPoliciesLoading] = useState(false);
  const [selectedPaymentPolicy, setSelectedPaymentPolicy] = useState<string>('');
  const [selectedFulfillmentPolicy, setSelectedFulfillmentPolicy] = useState<string>('');
  const [selectedReturnPolicy, setSelectedReturnPolicy] = useState<string>('');
  const [categories, setCategories] = useState<CategoriesResponse | null>(null);
  const [categoriesLoading, setCategoriesLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [categoryAspects, setCategoryAspects] = useState<AspectsResponse | null>(null);
  const [aspectsLoading, setAspectsLoading] = useState(false);
  const [featuresInputValue, setFeaturesInputValue] = useState<string>('');
  const [leafCategories, setLeafCategories] = useState<LeafCategory[]>([]);
  const [selectedCategoryForExtraction, setSelectedCategoryForExtraction] = useState<string>('261186');
  const [extracting, setExtracting] = useState(false);
  
  // Local state for all editable fields to prevent re-render interruptions
  const [localBookFields, setLocalBookFields] = useState<Partial<Book>>({});
  const [localSpecificsFields, setLocalSpecificsFields] = useState<Record<string, any>>({});

  const currentBook = books[currentIndex];

  const loadBooks = useCallback(async () => {
    setLoading(true);
    try {
      // If filter is 'all', fetch all books without status filter
      const queueBooks = filter === 'all'
        ? await booksApi.getQueue()
        : await booksApi.getQueue(filter);

      // Filter out books with status 'exported' when showing 'all' (keep 'new' books)
      const filteredBooks = filter === 'all'
        ? queueBooks.filter(book =>
            book.status !== 'exported'
          )
        : queueBooks;

      setBooks(filteredBooks);
      setCurrentIndex(0);
    } catch (error) {
      console.error('Failed to load books:', error);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    loadBooks();
    checkOAuthStatus();
    // Fetch leaf categories for AI extraction
    fetchLeafCategories().then(setLeafCategories).catch(() => setLeafCategories([]));
  }, [loadBooks]);

  // Reset policy selections when book changes
  useEffect(() => {
    setSelectedPaymentPolicy('');
    setSelectedFulfillmentPolicy('');
    setSelectedReturnPolicy('');
    setSelectedCategory('');
    setCategoryAspects(null);
    // Sync local state with book data when book changes
    if (currentBook) {
      // Sync book fields
      setLocalBookFields({
        title_ai: currentBook.title_ai || '',
        title: currentBook.title || '',
        author: currentBook.author || '',
        isbn13: currentBook.isbn13 || '',
        language: currentBook.language || '',
        publisher: currentBook.publisher || '',
        year: currentBook.year || '',
        edition: currentBook.edition || '',
        format: currentBook.format || '',
        condition_grade: currentBook.condition_grade || '',
        defects: currentBook.defects || '',
        price_suggested: currentBook.price_suggested ?? undefined,
        description_ai: currentBook.description_ai || '',
      });
      // Sync specifics fields
      const specifics = currentBook.specifics_ai || {};
      setLocalSpecificsFields({
        isbn10: specifics.isbn10 || '',
        country_of_manufacture: specifics.country_of_manufacture || '',
        narrative_type: specifics.narrative_type || '',
        genre: Array.isArray(specifics.genre) ? specifics.genre.join(', ') : (specifics.genre || ''),
        topic: Array.isArray(specifics.topic) ? specifics.topic.join(', ') : (specifics.topic || ''),
        type: specifics.type || '',
        era: specifics.era || '',
        illustrator: specifics.illustrator || '',
        literary_movement: specifics.literary_movement || '',
        book_series: specifics.book_series || '',
        intended_audience: Array.isArray(specifics.intended_audience) ? specifics.intended_audience.join(', ') : (specifics.intended_audience || ''),
        signed_by: specifics.signed_by || '',
      });
      // Sync features
      const features = specifics.features;
      setFeaturesInputValue(
        Array.isArray(features) 
          ? features.join(', ') 
          : (features || '')
      );
    } else {
      setLocalBookFields({});
      setLocalSpecificsFields({});
      setFeaturesInputValue('');
    }
  }, [currentBook?.id, currentBook?.specifics_ai]);

  const checkOAuthStatus = async () => {
    try {
      const status = await ebayOAuthApi.getStatus();
      setOAuthConnected(status.connected);
      // Load categories always (uses app-level OAuth, doesn't require user auth)
      loadCategories();
      // Load policies only if user is connected
      if (status.connected) {
        loadPolicies();
      }
    } catch (error) {
      console.error('Failed to check OAuth status:', error);
      setOAuthConnected(false);
      // Still try to load categories even if OAuth check fails
      loadCategories();
    }
  };

  const loadPolicies = async () => {
    setPoliciesLoading(true);
    try {
      const policiesData = await ebayPoliciesApi.getPolicies();
      setPolicies(policiesData);
    } catch (error: any) {
      console.error('Failed to load policies:', error);
      // Don't show toast - policies are optional
    } finally {
      setPoliciesLoading(false);
    }
  };

  const loadCategories = async () => {
    setCategoriesLoading(true);
    try {
      const categoriesData = await ebayCategoriesApi.getLeafCategories();
      setCategories(categoriesData);
    } catch (error: any) {
      console.error('Failed to load categories:', error);
      // Don't show toast - categories are optional
    } finally {
      setCategoriesLoading(false);
    }
  };

  // Load aspects when category changes
  useEffect(() => {
    const fn = async () => {
      if (!selectedCategory) {
        setCategoryAspects(null);
        return;
      }
      setAspectsLoading(true);
      try {
        const aspects = await ebayCategoriesApi.getCategoryAspects(selectedCategory);
        setCategoryAspects(aspects);
      } catch (e) {
        console.error('Failed to load aspects:', e);
        setCategoryAspects(null);
      } finally {
        setAspectsLoading(false);
      }
    };
    fn();
  }, [selectedCategory]);

  // Handle aspect value change bound to specifics_ai
  const handleAspectChange = async (aspectName: string, value: string) => {
    if (!currentBook) return;
    const nextSpecifics = { ...(currentBook.specifics_ai || {}) } as Record<string, any>;
    nextSpecifics[aspectName] = value;
    try {
      await booksApi.updateBook(currentBook.id, { specifics_ai: nextSpecifics as any });
      // Optimistically update local state
      const updated = [...books];
      updated[currentIndex] = { ...currentBook, specifics_ai: nextSpecifics } as any;
      setBooks(updated);
    } catch (e: any) {
      toast({ title: 'Failed to update aspect', description: e.message || 'Unknown error', variant: 'destructive' });
    }
  };

  const enrichMetadata = useCallback(async (bookId: string) => {
    const res = await fetch('/api/enrich', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ bookId }),
    });

    if (!res.ok) {
      const errorText = await res.text();
      let errorMessage = 'Unknown error occurred';
      try {
        const errorData = JSON.parse(errorText);
        errorMessage = errorData.error || errorMessage;
      } catch {
        errorMessage = errorText || `HTTP ${res.status}`;
      }
      throw new Error(errorMessage);
    }

    const data = await res.json();
    
    // Handle 200 response with errors (non-fatal errors like missing provider)
    if (data.errors && data.errors.length > 0) {
      const errorMessage = data.message || data.errors.join(', ');
      toast({
        title: 'Enrichment warning',
        description: errorMessage,
        variant: 'destructive',
      });
      // Don't throw - return data so UI can continue
      return data;
    }
    
    return data;
  }, [toast]);

  // Auto-enrich on load if book is missing core fields or AI fields
  useEffect(() => {
    if (!currentBook || loading) return;

    const needsEnrichment = 
      !currentBook.title || 
      !currentBook.author || 
      !currentBook.title_ai || 
      !currentBook.description_ai;

    if (needsEnrichment && currentBook.images && currentBook.images.length > 0) {
      // Auto-enrich in the background without blocking UI
      enrichMetadata(currentBook.id).then(() => {
        // Reload books after successful enrichment (even if errors occurred)
        loadBooks();
      }).catch((error) => {
        console.error('Auto-enrichment failed:', error);
        // Don't show toast for auto-enrichment failures - user can manually trigger
      });
    }
  }, [currentBook?.id, loading, enrichMetadata, loadBooks]);

  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (!currentBook) return;
      
      switch (e.key.toLowerCase()) {
        case 'a':
          handleApprove();
          break;
        case 's':
          handleSkip();
          break;
        case 'r':
          handleRegenerate();
          break;
        case 'l':
          handleLookup();
          break;
        case 'o':
          handleRerunOCR();
          break;
        case 'arrowup':
          navigatePrevious();
          break;
        case 'arrowdown':
          navigateNext();
          break;
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [currentBook]);

  const navigateNext = () => {
    if (currentIndex < books.length - 1) {
      setCurrentIndex(currentIndex + 1);
    }
  };

  const navigatePrevious = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
    }
  };

  const handleApprove = async () => {
    if (!currentBook) return;
    
    setLoading(true);
    try {
      await booksApi.updateBook(currentBook.id, { status: 'approved' });
      toast({
        title: 'Book approved',
        description: 'Book status updated to approved',
      });
      await loadBooks();
    } catch (error: any) {
      toast({
        title: 'Failed to approve book',
        description: error.message || 'Unknown error occurred',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = () => {
    navigateNext();
  };

  const handleRegenerate = async () => {
    if (!currentBook) return;
    
    setLoading(true);
    try {
      const result = await enrichMetadata(currentBook.id);
      // Only show success toast if no errors occurred
      if (!result?.errors || result.errors.length === 0) {
        toast({
          title: 'AI draft regenerated',
          description: 'New AI-generated title and description created',
        });
      }
      await loadBooks();
    } catch (error: any) {
      toast({
        title: 'Failed to regenerate AI draft',
        description: error.message || 'Unknown error occurred',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleLookup = async () => {
    if (!currentBook) return;
    
    setLoading(true);
    try {
      const result = await enrichMetadata(currentBook.id);
      // Only show success toast if no errors occurred
      if (!result?.errors || result.errors.length === 0) {
        toast({
          title: 'Metadata enriched',
          description: 'Book metadata updated from external sources',
        });
      }
      await loadBooks();
    } catch (error: any) {
      toast({
        title: 'Failed to enrich metadata',
        description: error.message || 'Unknown error occurred',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleRerunOCR = async () => {
    if (!currentBook) return;
    
    setLoading(true);
    try {
      const result = await enrichMetadata(currentBook.id);
      // Only show success toast if no errors occurred
      if (!result?.errors || result.errors.length === 0) {
        toast({
          title: 'OCR rerun',
          description: 'Scanning book images again',
        });
      }
      await loadBooks();
    } catch (error: any) {
      toast({
        title: 'Failed to rerun OCR',
        description: error.message || 'Unknown error occurred',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const runAIExtraction = async (categoryId: string) => {
    if (!currentBook) return;
    
    setExtracting(true);
    try {
      const res = await fetch(`${API_BASE_URL}/ai/vision/${currentBook.id}?category_id=${encodeURIComponent(categoryId)}`, {
        method: 'POST',
      });
      
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(errorData.detail || `Extraction failed: ${res.status}`);
      }
      
      const data = await res.json();
      
      if (!data.ok) {
        const errorMsg = data.errors?.join(', ') || 'Extraction failed';
        toast({
          title: 'Extraction failed',
          description: errorMsg,
          variant: 'destructive',
        });
        return;
      }
      
      // Update book state: merge extracted data, set status to 'auto', set ebay_category_id
      const updatedBooks = [...books];
      const bookIndex = updatedBooks.findIndex(b => b.id === currentBook.id);
      if (bookIndex !== -1) {
        updatedBooks[bookIndex] = {
          ...updatedBooks[bookIndex],
          ...data.mapped_fields,
          status: 'auto' as const,
          ebay_category_id: categoryId,
        };
        setBooks(updatedBooks);
      }
      
      toast({
        title: 'Extraction successful',
        description: 'Book metadata extracted and updated',
      });
      
      // Reload books to get latest state from server
      await loadBooks();
    } catch (error: any) {
      toast({
        title: 'Failed to extract with AI',
        description: error.message || 'Unknown error occurred',
        variant: 'destructive',
      });
    } finally {
      setExtracting(false);
    }
  };

  const handleVerify = async () => {
    if (!currentBook) return;
    
    setLoading(true);
    try {
      await booksApi.verifyBook(currentBook.id);
      toast({
        title: 'Book verified',
        description: 'Book is ready for export',
      });
      await loadBooks();
    } catch (error: any) {
      toast({
        title: 'Failed to verify book',
        description: error.message || 'Unknown error occurred',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSaveDraft = async () => {
    if (!currentBook) return;

    // Check OAuth status first
    if (oauthConnected === false) {
      toast({
        title: 'eBay account not connected',
        description: 'Please connect your eBay account in Settings first',
        variant: 'destructive',
        action: (
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.location.href = '/settings'}
          >
            Go to Settings
          </Button>
        ),
      });
      return;
    }

    if (!currentBook.verified) {
      toast({
        title: 'Book not verified',
        description: 'Please verify the book before saving draft',
        variant: 'destructive',
      });
      return;
    }

    if (!currentBook.price_suggested) {
      toast({
        title: 'Price required',
        description: 'Please set a Buy It Now price before saving draft',
        variant: 'destructive',
      });
      return;
    }

    setPublishLoading(true);
    try {
      const result = await ebayPublishHelper.saveDraft(currentBook.id, {
        payment_policy_id: selectedPaymentPolicy || undefined,
        fulfillment_policy_id: selectedFulfillmentPolicy || undefined,
        return_policy_id: selectedReturnPolicy || undefined,
        category_id: selectedCategory || undefined,
      });
      if (result.success) {
        toast({
          title: 'Draft saved successfully!',
          description: 'Listing created as draft on eBay. You can publish it later from Seller Hub.',
        });
        await loadBooks();
        await checkOAuthStatus();
      } else {
        toast({
          title: 'Failed to save draft',
          description: result.error || 'Unknown error occurred',
          variant: 'destructive',
        });
      }
    } catch (error: any) {
      toast({
        title: 'Failed to save draft',
        description: error.message || 'Unknown error occurred',
        variant: 'destructive',
      });
    } finally {
      setPublishLoading(false);
    }
  };

  const handlePublish = async () => {
    if (!currentBook) return;

    // Check OAuth status first
    if (oauthConnected === false) {
      toast({
        title: 'eBay account not connected',
        description: 'Please connect your eBay account in Settings first',
        variant: 'destructive',
        action: (
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.location.href = '/settings'}
          >
            Go to Settings
          </Button>
        ),
      });
      return;
    }

    if (!currentBook.verified) {
      toast({
        title: 'Book not verified',
        description: 'Please verify the book before publishing',
        variant: 'destructive',
      });
      return;
    }

    if (!currentBook.price_suggested) {
      toast({
        title: 'Price required',
        description: 'Please set a Buy It Now price before publishing',
        variant: 'destructive',
      });
      return;
    }
    
    setPublishLoading(true);
    try {
      const result = await ebayPublishHelper.publishBook(currentBook.id, {
        payment_policy_id: selectedPaymentPolicy || undefined,
        fulfillment_policy_id: selectedFulfillmentPolicy || undefined,
        return_policy_id: selectedReturnPolicy || undefined,
        category_id: selectedCategory || undefined,
      });
      if (result.success) {
        toast({
          title: 'Book published successfully!',
          description: result.listing_url 
            ? 'Listing created on eBay'
            : 'Listing created on eBay',
          action: result.listing_url ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.open(result.listing_url!, '_blank')}
            >
              <ExternalLink className="h-3 w-3 mr-1" />
              View Listing
            </Button>
          ) : undefined,
        });
        if (result.listing_url) {
          // Optionally open listing URL in new tab after a short delay
          setTimeout(() => {
            window.open(result.listing_url, '_blank');
          }, 1000);
        }
        await loadBooks();
        await checkOAuthStatus(); // Refresh OAuth status
      } else {
        toast({
          title: 'Failed to publish book',
          description: result.error || 'Unknown error occurred',
          variant: 'destructive',
        });
      }
    } catch (error: any) {
      toast({
        title: 'Failed to publish book',
        description: error.message || 'Unknown error occurred',
        variant: 'destructive',
      });
    } finally {
      setPublishLoading(false);
    }
  };

  const updateBookField = async (field: keyof Book, value: any) => {
    if (!currentBook) return;
    
    try {
      await booksApi.updateBook(currentBook.id, { [field]: value });
      await loadBooks();
    } catch (error) {
      console.error('Failed to update book:', error);
    }
  };

  const updateSpecificsField = async (field: string, value: any) => {
    if (!currentBook) return;
    
    try {
      const specifics = currentBook.specifics_ai || {};
      const updatedSpecifics = { ...specifics, [field]: value };
      // Remove field if value is empty/null
      if (value === null || value === '' || (Array.isArray(value) && value.length === 0)) {
        delete updatedSpecifics[field];
      }
      await booksApi.updateBook(currentBook.id, { specifics_ai: updatedSpecifics });
      await loadBooks();
    } catch (error) {
      console.error('Failed to update specifics field:', error);
    }
  };

  const getSpecificsValue = (field: string, defaultValue: any = null) => {
    if (!currentBook?.specifics_ai) return defaultValue;
    return currentBook.specifics_ai[field] ?? defaultValue;
  };

  if (loading && books.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex flex-col items-center gap-2">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          <p className="text-muted-foreground">Loading books...</p>
        </div>
      </div>
    );
  }

  if (!currentBook) {
    return (
      <div className="container mx-auto p-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-4">No books to review</h1>
          <p className="text-muted-foreground">Upload some images to get started!</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <h1 className="text-2xl font-bold">Review Books</h1>
            <Badge variant="secondary">
              {currentIndex + 1} / {books.length}
            </Badge>
            {currentBook.verified && (
              <Badge variant="default" className="bg-green-600">
                <CheckCircle className="h-3 w-3 mr-1" />
                Verified
              </Badge>
            )}
            {currentBook.exported && (
              <Badge variant="outline">
                Exported
              </Badge>
            )}
            {currentBook.publish_status === 'published' && (
              <Badge variant="default" className="bg-blue-600">
                Published
              </Badge>
            )}
            {currentBook.ebay_listing_id && (
              <Badge 
                variant="outline" 
                className="cursor-pointer hover:bg-muted" 
                onClick={() => {
                  const url = currentBook.ebay_listing_id?.startsWith('http') 
                    ? currentBook.ebay_listing_id 
                    : `https://www.ebay.com/itm/${currentBook.ebay_listing_id}`;
                  window.open(url, '_blank');
                }}
              >
                <ExternalLink className="h-3 w-3 mr-1" />
                eBay Listing
              </Badge>
            )}
            {oauthConnected === false && (
              <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-200">
                OAuth Not Connected
              </Badge>
            )}
            <Select value={filter} onValueChange={setFilter}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Books</SelectItem>
                <SelectItem value="auto">Auto-Extracted</SelectItem>
                <SelectItem value="needs_review">Needs Review</SelectItem>
                <SelectItem value="approved">Approved</SelectItem>
                <SelectItem value="new">New (No Data)</SelectItem>
                <SelectItem value="exported">Exported</SelectItem>
              </SelectContent>
            </Select>
          </div>
          
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={navigatePrevious}
              disabled={currentIndex === 0}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={navigateNext}
              disabled={currentIndex === books.length - 1}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: Images */}
          <div>
            <Card>
              <CardHeader>
                <CardTitle>Images</CardTitle>
              </CardHeader>
              <CardContent>
                <ImageCarousel images={currentBook.images} bookId={currentBook.id} />
              </CardContent>
            </Card>
          </div>

          {/* Right: Details */}
          <div className="space-y-4">
            {/* Core Fields */}
            <Card>
              <CardHeader>
                <CardTitle>Core Fields</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="title_ai">eBay Title (AI)</Label>
                  <Input
                    id="title_ai"
                    value={localBookFields.title_ai || ''}
                    onChange={(e) => setLocalBookFields({...localBookFields, title_ai: e.target.value})}
                    onBlur={() => updateBookField('title_ai', localBookFields.title_ai || '')}
                    maxLength={80}
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    {(localBookFields.title_ai || '').length}/80 characters
                  </p>
                </div>
                <div>
                  <Label htmlFor="title">Book Title</Label>
                  <Input
                    id="title"
                    value={localBookFields.title || ''}
                    onChange={(e) => setLocalBookFields({...localBookFields, title: e.target.value})}
                    onBlur={() => updateBookField('title', localBookFields.title || '')}
                  />
                </div>
                <div>
                  <Label htmlFor="author">Author</Label>
                  <Input
                    id="author"
                    value={localBookFields.author || ''}
                    onChange={(e) => setLocalBookFields({...localBookFields, author: e.target.value})}
                    onBlur={() => updateBookField('author', localBookFields.author || '')}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="isbn13">ISBN-13</Label>
                    <Input
                      id="isbn13"
                      value={localBookFields.isbn13 || ''}
                      onChange={(e) => setLocalBookFields({...localBookFields, isbn13: e.target.value})}
                      onBlur={() => updateBookField('isbn13', localBookFields.isbn13 || '')}
                    />
                  </div>
                  <div>
                    <Label htmlFor="isbn10">ISBN-10</Label>
                    <Input
                      id="isbn10"
                      value={localSpecificsFields.isbn10 || ''}
                      onChange={(e) => setLocalSpecificsFields({...localSpecificsFields, isbn10: e.target.value})}
                      onBlur={() => updateSpecificsField('isbn10', localSpecificsFields.isbn10 || null)}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="language">Language</Label>
                    <Input
                      id="language"
                      value={localBookFields.language || ''}
                      onChange={(e) => setLocalBookFields({...localBookFields, language: e.target.value})}
                      onBlur={() => updateBookField('language', localBookFields.language || '')}
                    />
                  </div>
                  <div>
                    <Label htmlFor="country_of_manufacture">Country/Region of Manufacture</Label>
                    <Input
                      id="country_of_manufacture"
                      value={localSpecificsFields.country_of_manufacture || ''}
                      onChange={(e) => setLocalSpecificsFields({...localSpecificsFields, country_of_manufacture: e.target.value})}
                      onBlur={() => updateSpecificsField('country_of_manufacture', localSpecificsFields.country_of_manufacture || null)}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="publisher">Publisher</Label>
                    <Input
                      id="publisher"
                      value={localBookFields.publisher || ''}
                      onChange={(e) => setLocalBookFields({...localBookFields, publisher: e.target.value})}
                      onBlur={() => updateBookField('publisher', localBookFields.publisher || '')}
                    />
                  </div>
                  <div>
                    <Label htmlFor="year">Publication Year</Label>
                    <Input
                      id="year"
                      value={localBookFields.year || ''}
                      onChange={(e) => setLocalBookFields({...localBookFields, year: e.target.value})}
                      onBlur={() => updateBookField('year', localBookFields.year || '')}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="edition">Edition</Label>
                    <Input
                      id="edition"
                      value={localBookFields.edition || ''}
                      onChange={(e) => setLocalBookFields({...localBookFields, edition: e.target.value})}
                      onBlur={() => updateBookField('edition', localBookFields.edition || '')}
                    />
                  </div>
                  <div>
                    <Label htmlFor="narrative_type">Narrative Type</Label>
                    <Input
                      id="narrative_type"
                      value={localSpecificsFields.narrative_type || ''}
                      onChange={(e) => setLocalSpecificsFields({...localSpecificsFields, narrative_type: e.target.value})}
                      onBlur={() => updateSpecificsField('narrative_type', localSpecificsFields.narrative_type || null)}
                    />
                  </div>
                </div>
                <div>
                  <Label htmlFor="format">Format</Label>
                  <Input
                    id="format"
                    value={localBookFields.format || ''}
                    onChange={(e) => setLocalBookFields({...localBookFields, format: e.target.value})}
                    onBlur={() => updateBookField('format', localBookFields.format || '')}
                    placeholder="e.g., Hardcover, Paperback, Dust Jacket"
                  />
                </div>
                <div>
                  <Label htmlFor="genre">Genre</Label>
                  <Input
                    id="genre"
                    value={localSpecificsFields.genre || ''}
                    onChange={(e) => setLocalSpecificsFields({...localSpecificsFields, genre: e.target.value})}
                    onBlur={() => {
                      const genres = localSpecificsFields.genre ? localSpecificsFields.genre.split(',').map(g => g.trim()).filter(g => g) : [];
                      updateSpecificsField('genre', genres.length > 0 ? genres : null);
                    }}
                    placeholder="Comma-separated genres"
                  />
                </div>
                <div>
                  <Label htmlFor="topic">Topic/Subject</Label>
                  <Input
                    id="topic"
                    value={localSpecificsFields.topic || ''}
                    onChange={(e) => setLocalSpecificsFields({...localSpecificsFields, topic: e.target.value})}
                    onBlur={() => {
                      const topics = localSpecificsFields.topic ? localSpecificsFields.topic.split(',').map(t => t.trim()).filter(t => t) : [];
                      updateSpecificsField('topic', topics.length > 0 ? topics : null);
                    }}
                    placeholder="Comma-separated topics"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="type">Type</Label>
                    <Input
                      id="type"
                      value={localSpecificsFields.type || ''}
                      onChange={(e) => setLocalSpecificsFields({...localSpecificsFields, type: e.target.value})}
                      onBlur={() => updateSpecificsField('type', localSpecificsFields.type || null)}
                    />
                  </div>
                  <div>
                    <Label htmlFor="era">Era</Label>
                    <Input
                      id="era"
                      value={localSpecificsFields.era || ''}
                      onChange={(e) => setLocalSpecificsFields({...localSpecificsFields, era: e.target.value})}
                      onBlur={() => updateSpecificsField('era', localSpecificsFields.era || null)}
                    />
                  </div>
                </div>
                <div>
                  <Label htmlFor="illustrator">Illustrator</Label>
                  <Input
                    id="illustrator"
                    value={localSpecificsFields.illustrator || ''}
                    onChange={(e) => setLocalSpecificsFields({...localSpecificsFields, illustrator: e.target.value})}
                    onBlur={() => updateSpecificsField('illustrator', localSpecificsFields.illustrator || null)}
                  />
                </div>
                <div>
                  <Label htmlFor="literary_movement">Literary Movement</Label>
                  <Input
                    id="literary_movement"
                    value={localSpecificsFields.literary_movement || ''}
                    onChange={(e) => setLocalSpecificsFields({...localSpecificsFields, literary_movement: e.target.value})}
                    onBlur={() => updateSpecificsField('literary_movement', localSpecificsFields.literary_movement || null)}
                  />
                </div>
                <div>
                  <Label htmlFor="book_series">Book Series</Label>
                  <Input
                    id="book_series"
                    value={localSpecificsFields.book_series || ''}
                    onChange={(e) => setLocalSpecificsFields({...localSpecificsFields, book_series: e.target.value})}
                    onBlur={() => updateSpecificsField('book_series', localSpecificsFields.book_series || null)}
                  />
                </div>
                <div>
                  <Label htmlFor="intended_audience">Intended Audience</Label>
                  <Input
                    id="intended_audience"
                    value={localSpecificsFields.intended_audience || ''}
                    onChange={(e) => setLocalSpecificsFields({...localSpecificsFields, intended_audience: e.target.value})}
                    onBlur={() => {
                      const audiences = localSpecificsFields.intended_audience ? localSpecificsFields.intended_audience.split(',').map(a => a.trim()).filter(a => a) : [];
                      updateSpecificsField('intended_audience', audiences.length > 0 ? audiences : null);
                    }}
                    placeholder="Comma-separated audiences"
                  />
                </div>
              </CardContent>
            </Card>

            {/* Book Attributes */}
            <Card>
              <CardHeader>
                <CardTitle>Book Attributes</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="signed"
                      checked={getSpecificsValue('features', []).includes('Signed')}
                      onCheckedChange={(checked) => {
                        const features = getSpecificsValue('features', []) || [];
                        const updatedFeatures = checked
                          ? [...features.filter(f => f !== 'Signed'), 'Signed']
                          : features.filter(f => f !== 'Signed');
                        updateSpecificsField('features', updatedFeatures.length > 0 ? updatedFeatures : null);
                      }}
                    />
                    <Label htmlFor="signed" className="cursor-pointer">Signed</Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="inscribed"
                      checked={getSpecificsValue('features', []).includes('Inscribed')}
                      onCheckedChange={(checked) => {
                        const features = getSpecificsValue('features', []) || [];
                        const updatedFeatures = checked
                          ? [...features.filter(f => f !== 'Inscribed'), 'Inscribed']
                          : features.filter(f => f !== 'Inscribed');
                        updateSpecificsField('features', updatedFeatures.length > 0 ? updatedFeatures : null);
                      }}
                    />
                    <Label htmlFor="inscribed" className="cursor-pointer">Inscribed</Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="vintage"
                      checked={getSpecificsValue('features', []).includes('Vintage')}
                      onCheckedChange={(checked) => {
                        const features = getSpecificsValue('features', []) || [];
                        const updatedFeatures = checked
                          ? [...features.filter(f => f !== 'Vintage'), 'Vintage']
                          : features.filter(f => f !== 'Vintage');
                        updateSpecificsField('features', updatedFeatures.length > 0 ? updatedFeatures : null);
                      }}
                    />
                    <Label htmlFor="vintage" className="cursor-pointer">Vintage</Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="ex_libris"
                      checked={getSpecificsValue('ex_libris', false)}
                      onCheckedChange={(checked) => updateSpecificsField('ex_libris', checked || null)}
                    />
                    <Label htmlFor="ex_libris" className="cursor-pointer">Ex Libris</Label>
                  </div>
                </div>
                <div>
                  <Label htmlFor="signed_by">Signed By</Label>
                  <Input
                    id="signed_by"
                    value={localSpecificsFields.signed_by || ''}
                    onChange={(e) => setLocalSpecificsFields({...localSpecificsFields, signed_by: e.target.value})}
                    onBlur={() => updateSpecificsField('signed_by', localSpecificsFields.signed_by || null)}
                  />
                </div>
                <div>
                  <Label htmlFor="features">Features</Label>
                  <Input
                    id="features"
                    value={featuresInputValue}
                    onChange={(e) => {
                      setFeaturesInputValue(e.target.value);
                    }}
                    onBlur={async () => {
                      const features = featuresInputValue ? featuresInputValue.split(',').map(f => f.trim()).filter(f => f) : [];
                      await updateSpecificsField('features', features.length > 0 ? features : null);
                    }}
                    placeholder="Comma-separated features (e.g., First Edition, Dust Jacket, Illustrated)"
                  />
                </div>
              </CardContent>
            </Card>

            {/* AI Output */}
            <Card>
              <CardHeader>
                <CardTitle>AI Output Preview</CardTitle>
                {localBookFields.title_ai && (
                  <Badge variant="outline">
                    Title: {localBookFields.title_ai.length}/80 chars
                  </Badge>
                )}
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="title_ai">AI Title</Label>
                  <Textarea
                    id="title_ai"
                    value={localBookFields.title_ai || ''}
                    onChange={(e) => setLocalBookFields({...localBookFields, title_ai: e.target.value})}
                    onBlur={() => updateBookField('title_ai', localBookFields.title_ai || '')}
                    rows={2}
                  />
                </div>
                <div>
                  <Label htmlFor="description_ai">AI Description</Label>
                  <Textarea
                    id="description_ai"
                    value={localBookFields.description_ai || ''}
                    onChange={(e) => setLocalBookFields({...localBookFields, description_ai: e.target.value})}
                    onBlur={() => updateBookField('description_ai', localBookFields.description_ai || '')}
                    rows={4}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Condition & Price */}
            <Card>
              <CardHeader>
                <CardTitle>Condition & Price</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="condition_grade">Physical Condition</Label>
                  <Select
                    value={localBookFields.condition_grade || currentBook.condition_grade || ''}
                    onValueChange={(value: any) => {
                      setLocalBookFields({...localBookFields, condition_grade: value});
                      updateBookField('condition_grade', value);
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Brand New">Brand New</SelectItem>
                      <SelectItem value="Like New">Like New</SelectItem>
                      <SelectItem value="Very Good">Very Good</SelectItem>
                      <SelectItem value="Good">Good</SelectItem>
                      <SelectItem value="Acceptable">Acceptable</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="defects">Defects</Label>
                  <Textarea
                    id="defects"
                    value={localBookFields.defects || ''}
                    onChange={(e) => setLocalBookFields({...localBookFields, defects: e.target.value})}
                    onBlur={() => updateBookField('defects', localBookFields.defects || '')}
                    rows={2}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="price_suggested">Buy It Now Price (Required)</Label>
                    <Input
                      id="price_suggested"
                      type="number"
                      step="0.01"
                      value={localBookFields.price_suggested !== undefined ? localBookFields.price_suggested : ''}
                      onChange={(e) => setLocalBookFields({...localBookFields, price_suggested: e.target.value ? parseFloat(e.target.value) : undefined})}
                      onBlur={() => updateBookField('price_suggested', localBookFields.price_suggested !== undefined ? localBookFields.price_suggested : null)}
                      placeholder="0.00"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      The fixed price buyers will pay
                    </p>
                  </div>
                  <div>
                    <Label htmlFor="quantity">Quantity</Label>
                    <Input
                      id="quantity"
                      type="number"
                      step="1"
                      min="1"
                      value={currentBook.quantity || 1}
                      onChange={(e) => updateBookField('quantity', parseInt(e.target.value) || 1)}
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Number of items available
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Publishing Requirements Status */}
            {currentBook.publish_status !== 'published' && (
              <Card className="bg-muted/50">
                <CardContent className="pt-6">
                  <h3 className="font-semibold mb-3 text-sm">Publishing Requirements:</h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center gap-2">
                      {currentBook.verified ? (
                        <CheckCircle className="h-4 w-4 text-green-600" />
                      ) : (
                        <div className="h-4 w-4 rounded-full border-2 border-muted-foreground" />
                      )}
                      <span className={currentBook.verified ? "text-green-600" : ""}>
                        Book verified
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {currentBook.price_suggested ? (
                        <CheckCircle className="h-4 w-4 text-green-600" />
                      ) : (
                        <div className="h-4 w-4 rounded-full border-2 border-muted-foreground" />
                      )}
                      <span className={currentBook.price_suggested ? "text-green-600" : ""}>
                        Starting price set
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {oauthConnected ? (
                        <CheckCircle className="h-4 w-4 text-green-600" />
                      ) : (
                        <div className="h-4 w-4 rounded-full border-2 border-muted-foreground" />
                      )}
                      <span className={oauthConnected ? "text-green-600" : ""}>
                        eBay account connected
                      </span>
                      {!oauthConnected && (
                        <Button
                          variant="link"
                          size="sm"
                          className="h-auto p-0 text-xs"
                          onClick={() => window.location.href = '/settings'}
                        >
                          (Connect in Settings)
                        </Button>
                      )}
                    </div>

                    {/* Existing eBay Offer Indicator */}
                    <div className="flex items-center gap-2">
                      {currentBook.ebay_offer_id ? (
                        <FileCheck className="h-4 w-4 text-blue-600" />
                      ) : (
                        <div className="h-4 w-4 rounded-full border-2 border-muted-foreground" />
                      )}
                      <span className={currentBook.ebay_offer_id ? "text-blue-600 font-medium" : "text-muted-foreground"}>
                        {currentBook.ebay_offer_id ? (
                          <>
                            eBay offer exists
                            <span className="ml-2 text-xs opacity-75">
                              (ID: {currentBook.ebay_offer_id})
                            </span>
                          </>
                        ) : (
                          "No eBay offer yet"
                        )}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* eBay Policy Selection */}
            {oauthConnected && currentBook.publish_status !== 'published' && (
              <Card className="bg-blue-50 dark:bg-blue-950/20">
                <CardHeader>
                  <CardTitle className="text-base">eBay Business Policies</CardTitle>
                  <p className="text-sm text-muted-foreground">
                    Select payment, shipping, and return policies for this listing
                  </p>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Category Selection */}
                  {/* Category Selection */}
                  <div className="space-y-2">
                    <Label htmlFor="category" className="flex items-center gap-2">
                      <BookOpen className="h-4 w-4" />
                      Category
                    </Label>
                    <Select
                      value={selectedCategory}
                      onValueChange={setSelectedCategory}
                      disabled={categoriesLoading}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select category (optional - will auto-select if not chosen)" />
                      </SelectTrigger>
                      <SelectContent>
                        {categories?.categories && categories.categories.length > 0 ? (
                          categories.categories.map((category) => (
                            <SelectItem key={category.category_id} value={category.category_id}>
                              {category.name} ({category.category_id})
                            </SelectItem>
                          ))
                        ) : (
                          <SelectItem value="no-categories" disabled>
                            {categoriesLoading ? 'Loading...' : 'No categories available'}
                          </SelectItem>
                        )}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      Select a leaf category for this listing. If not selected, will auto-select based on book content.
                    </p>
                  </div>

                  {/* Dynamic Aspects for selected category */}
                  {selectedCategory && (
                    <div className="space-y-3">
                      <div className="text-sm font-medium">Additional Category Fields</div>
                      <p className="text-xs text-muted-foreground">
                        These are category-specific fields. Core fields like Author, Title, and Publisher are already in the main form above.
                      </p>
                      {aspectsLoading && (
                        <div className="flex items-center text-sm text-muted-foreground">
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" /> Loading aspects...
                        </div>
                      )}
                      {!aspectsLoading && categoryAspects?.aspects?.length === 0 && (
                        <div className="text-xs text-muted-foreground">No additional fields for this category.</div>
                      )}
                      {!aspectsLoading && categoryAspects?.aspects?.filter((a) => {
                        // Filter out core fields that already have dedicated inputs in the main form
                        const coreFields = [
                          'Author', 'Book Title', 'Title', 'Publisher', 'Language',
                          'Publication Year', 'Format', 'Edition', 'ISBN'
                        ];
                        return !coreFields.includes(a.name);
                      }).map((a) => {
                        // Determine if this should be a dropdown or text input
                        // Use dropdown ONLY if aspect_mode is SELECTION_ONLY or if it has few recommended values
                        const useDropdown = a.aspect_mode === 'SELECTION_ONLY' ||
                          (a.recommended_values && a.recommended_values.length > 0 && a.recommended_values.length <= 20);

                        return (
                          <div key={a.name} className="space-y-1">
                            <Label className="text-xs">
                              {a.name}
                              {a.required && <span className="text-red-600 ml-1">*</span>}
                            </Label>
                            {useDropdown ? (
                              <Select
                                value={String((currentBook.specifics_ai || {})[a.name] || '')}
                                onValueChange={(v) => handleAspectChange(a.name, v)}
                              >
                                <SelectTrigger>
                                  <SelectValue placeholder={`Select ${a.name}`} />
                                </SelectTrigger>
                                <SelectContent>
                                  {a.recommended_values?.map((v) => (
                                    <SelectItem key={v} value={v}>{v}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            ) : (
                              <Input
                                value={String((currentBook.specifics_ai || {})[a.name] || '')}
                                onChange={(e) => handleAspectChange(a.name, e.target.value)}
                                placeholder={`Enter ${a.name}`}
                              />
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Payment Policy */}
                  <div className="space-y-2">
                    <Label htmlFor="payment_policy" className="flex items-center gap-2">
                      <CreditCard className="h-4 w-4" />
                      Payment Policy
                    </Label>
                    <Select
                      value={selectedPaymentPolicy}
                      onValueChange={setSelectedPaymentPolicy}
                      disabled={policiesLoading}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select payment policy" />
                      </SelectTrigger>
                      <SelectContent>
                        {policies?.payment_policies && policies.payment_policies.length > 0 ? (
                          policies.payment_policies.map((policy) => (
                            <SelectItem key={policy.policy_id} value={policy.policy_id}>
                              {policy.name}
                            </SelectItem>
                          ))
                        ) : (
                          <SelectItem value="no-policies" disabled>
                            {policiesLoading ? 'Loading...' : 'No payment policies available'}
                          </SelectItem>
                        )}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Fulfillment Policy */}
                  <div className="space-y-2">
                    <Label htmlFor="fulfillment_policy" className="flex items-center gap-2">
                      <Package className="h-4 w-4" />
                      Shipping (Fulfillment) Policy
                    </Label>
                    <Select
                      value={selectedFulfillmentPolicy}
                      onValueChange={setSelectedFulfillmentPolicy}
                      disabled={policiesLoading}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select fulfillment policy" />
                      </SelectTrigger>
                      <SelectContent>
                        {policies?.fulfillment_policies && policies.fulfillment_policies.length > 0 ? (
                          policies.fulfillment_policies.map((policy) => (
                            <SelectItem key={policy.policy_id} value={policy.policy_id}>
                              {policy.name}
                            </SelectItem>
                          ))
                        ) : (
                          <SelectItem value="no-policies" disabled>
                            {policiesLoading ? 'Loading...' : 'No fulfillment policies available'}
                          </SelectItem>
                        )}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Return Policy */}
                  <div className="space-y-2">
                    <Label htmlFor="return_policy" className="flex items-center gap-2">
                      <ArrowLeftRight className="h-4 w-4" />
                      Return Policy
                    </Label>
                    <Select
                      value={selectedReturnPolicy}
                      onValueChange={setSelectedReturnPolicy}
                      disabled={policiesLoading}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select return policy" />
                      </SelectTrigger>
                      <SelectContent>
                        {policies?.return_policies && policies.return_policies.length > 0 ? (
                          policies.return_policies.map((policy) => (
                            <SelectItem key={policy.policy_id} value={policy.policy_id}>
                              {policy.name}
                            </SelectItem>
                          ))
                        ) : (
                          <SelectItem value="no-policies" disabled>
                            {policiesLoading ? 'Loading...' : 'No return policies available'}
                          </SelectItem>
                        )}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Refresh Policies Button */}
                  <div className="pt-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        loadPolicies();
                        loadCategories();
                      }}
                      disabled={policiesLoading || categoriesLoading || aspectsLoading}
                      className="w-full"
                    >
                      {policiesLoading || categoriesLoading || aspectsLoading ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          Loading...
                        </>
                      ) : (
                        <>
                          <RefreshCw className="h-4 w-4 mr-2" />
                          Refresh Policies & Categories
                        </>
                      )}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* AI Extraction for New Books */}
            {currentBook.status === 'new' && (
              <Card className="bg-blue-50 dark:bg-blue-950/20 border-blue-200">
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <ScanLine className="h-5 w-5" />
                    Extract Book Metadata with AI
                  </CardTitle>
                  <p className="text-sm text-muted-foreground">
                    Select a category and extract book metadata from images using AI vision
                  </p>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="extraction_category">eBay Category</Label>
                    <Select
                      value={selectedCategoryForExtraction}
                      onValueChange={setSelectedCategoryForExtraction}
                      disabled={extracting}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select category" />
                      </SelectTrigger>
                      <SelectContent>
                        {leafCategories.length > 0 ? (
                          leafCategories.map((cat) => (
                            <SelectItem key={cat.category_id} value={cat.category_id}>
                              {cat.name} ({cat.category_id})
                            </SelectItem>
                          ))
                        ) : (
                          <SelectItem value="no-categories" disabled>
                            Loading categories...
                          </SelectItem>
                        )}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      Select a leaf category for this book listing
                    </p>
                  </div>
                  <Button
                    onClick={() => runAIExtraction(selectedCategoryForExtraction)}
                    disabled={extracting || !selectedCategoryForExtraction}
                    className="w-full"
                    size="lg"
                  >
                    {extracting ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Extracting...
                      </>
                    ) : (
                      <>
                        <ScanLine className="h-4 w-4 mr-2" />
                        Extract with AI
                      </>
                    )}
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* Actions */}
            <div className="flex gap-2 flex-wrap">
              <Button variant="outline" onClick={handleRegenerate}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Regenerate AI
              </Button>
              <Button variant="outline" onClick={handleSkip}>
                <SkipForward className="h-4 w-4 mr-2" />
                Next Book
              </Button>
              <Button
                variant="default"
                onClick={handleVerify}
                disabled={currentBook.verified}
                className={currentBook.verified ? "bg-green-600 hover:bg-green-700" : "bg-green-600 hover:bg-green-700"}
                size="lg"
              >
                <CheckCircle className="h-4 w-4 mr-2" />
                {currentBook.verified ? "✓ Verified" : "Verify Book"}
              </Button>
              <Button
                variant="outline"
                onClick={handleSaveDraft}
                disabled={
                  publishLoading ||
                  !currentBook.verified ||
                  currentBook.publish_status === 'published' ||
                  currentBook.publish_status === 'draft' ||
                  !currentBook.price_suggested ||
                  oauthConnected === false
                }
                size="lg"
              >
                {currentBook.publish_status === 'draft' ? "✓ Saved as Draft" : "Save as Draft"}
              </Button>
              <Button
                variant="default"
                onClick={handlePublish}
                disabled={
                  publishLoading ||
                  !currentBook.verified ||
                  currentBook.publish_status === 'published' ||
                  !currentBook.price_suggested ||
                  oauthConnected === false
                }
                className="bg-blue-600 hover:bg-blue-700"
                size="lg"
              >
                {publishLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Publishing...
                  </>
                ) : (
                  <>
                    <Upload className="h-4 w-4 mr-2" />
                    {currentBook.publish_status === 'published' ? "✓ Published to eBay" : "Publish to eBay"}
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}