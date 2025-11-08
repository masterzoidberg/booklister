'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

export default function Home() {
  const router = useRouter();
  const [queueEmpty, setQueueEmpty] = useState<boolean | null>(null);

  useEffect(() => {
    checkQueue();
  }, []);

  const checkQueue = async () => {
    try {
      const response = await fetch('http://127.0.0.1:8000/queue?status=needs_review');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const books = await response.json();
      if (books.length === 0) {
        router.push('/upload');
      } else {
        router.push('/review');
      }
    } catch (error: any) {
      // Silently handle backend unavailability - redirect to upload page
      // Individual pages that need the backend will show appropriate errors
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        // Backend is not running - silently redirect
        router.push('/upload');
      } else {
        // Other errors - still redirect but log for debugging
        console.error('Failed to check queue:', error);
        router.push('/upload');
      }
    }
  };

  if (queueEmpty === null) {
    return <div className="flex items-center justify-center min-h-screen">Loading...</div>;
  }

  return null; // Will redirect
}