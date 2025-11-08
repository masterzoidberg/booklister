'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useDropzone } from 'react-dropzone';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Upload, X, CheckCircle, Folder, Eye, EyeOff } from 'lucide-react';
import { uploadApi } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';

interface FolderGroup {
  folderName: string;
  files: File[];
}

export default function UploadPage() {
  const router = useRouter();
  const { toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [folderGroups, setFolderGroups] = useState<FolderGroup[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadComplete, setUploadComplete] = useState(false);
  const [ocrCapabilities, setOcrCapabilities] = useState<{tesseract: boolean, pyzbar: boolean, opencv: boolean} | null>(null);
  const [showOcrCapabilities, setShowOcrCapabilities] = useState(false);

  // Load OCR capabilities on mount
  useEffect(() => {
    // OCR capabilities loading removed - scanApi no longer available
    // This functionality can be restored if needed with a different API
  }, [toast]);

  const processFiles = useCallback((fileList: File[]) => {
    // Group files by folder structure
    const groups: FolderGroup[] = [];
    const flatFiles: File[] = [];

    fileList.forEach((file) => {
      flatFiles.push(file);
      
      // Extract folder path from file.webkitRelativePath if available
      if ((file as any).webkitRelativePath) {
        const pathParts = (file as any).webkitRelativePath.split('/');
        const folderName = pathParts[0] || 'Root';
        
        let existingGroup = groups.find(g => g.folderName === folderName);
        if (!existingGroup) {
          existingGroup = { folderName, files: [] };
          groups.push(existingGroup);
        }
        existingGroup.files.push(file);
      } else {
        // For files without folder info, group by name or put in "General"
        let existingGroup = groups.find(g => g.folderName === 'General');
        if (!existingGroup) {
          existingGroup = { folderName: 'General', files: [] };
          groups.push(existingGroup);
        }
        existingGroup.files.push(file);
      }
    });

    setFolderGroups(groups);
    setFiles(flatFiles);
  }, []);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    // Validate file sizes
    const oversizedFiles = acceptedFiles.filter(file => file.size > 10 * 1024 * 1024);
    if (oversizedFiles.length > 0) {
      toast({
        title: "File too large",
        description: `${oversizedFiles.length} file(s) exceed 10MB limit`,
        variant: "destructive",
      });
      return;
    }

    // Validate file types
    const invalidFiles = acceptedFiles.filter(file => {
      const ext = file.name.toLowerCase().split('.').pop();
      return !['jpg', 'jpeg', 'png', 'webp', 'tiff', 'tif'].includes(ext || '');
    });
    
    if (invalidFiles.length > 0) {
      toast({
        title: "Invalid file type",
        description: `${invalidFiles.length} file(s) are not valid images`,
        variant: "destructive",
      });
      return;
    }

    processFiles(acceptedFiles);
    toast({
      title: "Files added",
      description: `Added ${acceptedFiles.length} image(s) to upload queue`,
    });
  }, [processFiles, toast]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/*': ['.jpeg', '.jpg', '.png', '.webp', '.tiff', '.tif'],
    },
    multiple: true,
    // Enable directory upload for supported browsers
    useFsAccessApi: true,
  });

  const handleFolderSelect = () => {
    fileInputRef.current?.click();
  };

  const handleFileInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(event.target.files || []);
    if (selectedFiles.length > 0) {
      onDrop(selectedFiles);
    }
  };

  const removeFile = (index: number) => {
    const newFiles = files.filter((_, i) => i !== index);
    setFiles(newFiles);
    processFiles(newFiles);
  };

  const removeFolder = (folderName: string) => {
    const newFiles = files.filter(file => {
      if ((file as any).webkitRelativePath) {
        return !(file as any).webkitRelativePath.startsWith(folderName + '/');
      }
      return folderName !== 'General';
    });
    processFiles(newFiles);
  };

  const handleUpload = async () => {
    if (files.length === 0) return;

    setUploading(true);
    setUploadProgress(0);

    try {
      // Simulate progress
      const progressInterval = setInterval(() => {
        setUploadProgress((prev) => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + 10;
        });
      }, 100);

      const fileList = new DataTransfer();
      files.forEach((file) => fileList.items.add(file));
      
      // Create folder information mapping
      const folderInfo: Record<string, string> = {};
      folderGroups.forEach(group => {
        group.files.forEach(file => {
          folderInfo[file.name] = group.folderName;
        });
      });
      
      const createdBooks = await uploadApi.uploadImages(fileList.files, folderInfo);
      
      clearInterval(progressInterval);
      setUploadProgress(100);
      setUploadComplete(true);
      
      toast({
        title: "Upload successful!",
        description: `Created ${createdBooks.length} book${createdBooks.length === 1 ? '' : 's'} from ${folderGroups.length} folder${folderGroups.length === 1 ? '' : 's'}. Select a category on the review page to extract metadata with AI.`,
      });
      
      // Redirect to review after a short delay
      setTimeout(() => {
        router.push('/review');
      }, 1500);
    } catch (error: any) {
      console.error('Upload failed:', error);
      
      let errorMessage = "Upload failed";
      let errorDetail = "Please try again";
      
      if (error.error) {
        errorMessage = "Upload error";
        errorDetail = error.detail || error.message || "Unknown error occurred";
      } else if (error.message) {
        errorDetail = error.message;
      }
      
      toast({
        title: errorMessage,
        description: errorDetail,
        variant: "destructive",
      });
      
      setUploading(false);
      setUploadProgress(0);
    }
  };

  if (uploadComplete) {
    return (
      <div className="container mx-auto p-6">
        <div className="max-w-md mx-auto text-center">
          <CheckCircle className="h-16 w-16 text-green-500 mx-auto mb-4" />
          <h1 className="text-2xl font-bold mb-2">Upload Complete!</h1>
          <p className="text-muted-foreground mb-2">Select a category to extract metadata with AI</p>
          <p className="text-sm text-muted-foreground">Redirecting to review page...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-bold mb-6">Upload Book Images</h1>
        
        {/* Drop Zone */}
        <Card className="mb-6">
          <CardContent className="p-6">
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                isDragActive
                  ? 'border-primary bg-primary/10 dark:bg-primary/20'
                  : 'border-muted-foreground/25 hover:border-muted-foreground/50 dark:border-muted-foreground/40 dark:hover:border-muted-foreground/60'
              }`}
            >
              <input {...getInputProps()} />
              <Upload className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
              {isDragActive ? (
                <p className="text-lg font-medium">Drop the images here...</p>
              ) : (
                <div>
                  <p className="text-lg font-medium mb-2">
                    Drag & drop book images or folders here
                  </p>
                  <p className="text-muted-foreground mb-4">
                    or click to select files or folders
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Supports: JPEG, PNG, WebP, TIFF • Folders will be organized automatically
                  </p>
                </div>
              )}
            </div>
            
            {/* Alternative folder selection for better cross-browser support */}
            <div className="mt-4 text-center">
              <Button
                variant="outline"
                onClick={handleFolderSelect}
                className="gap-2"
              >
                <Folder className="h-4 w-4" />
                Select Folder (Alternative)
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/*"
                webkitdirectory=""
                directory=""
                className="hidden"
                onChange={handleFileInputChange}
              />
              <p className="text-xs text-muted-foreground mt-2">
                Use this button if drag-drop doesn't work for folders
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Folder Groups */}
        {folderGroups.length > 0 && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>Selected Folders ({folderGroups.length}) - {files.length} Images</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {folderGroups.map((group) => (
                  <div key={group.folderName} className="border rounded-lg p-4 dark:border-muted">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <Folder className="h-5 w-5 text-primary" />
                        <h3 className="font-medium">{group.folderName}</h3>
                        <Badge variant="secondary">{group.files.length} images</Badge>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeFolder(group.folderName)}
                        disabled={uploading}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {group.files.slice(0, 4).map((file, index) => (
                        <div key={index} className="text-xs text-muted-foreground truncate">
                          📷 {file.name}
                        </div>
                      ))}
                      {group.files.length > 4 && (
                        <div className="text-xs text-muted-foreground">
                          ... and {group.files.length - 4} more
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Upload Progress */}
        {uploading && (
          <Card className="mb-6">
            <CardContent className="p-6">
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>Uploading...</span>
                  <span>{uploadProgress}%</span>
                </div>
                <Progress value={uploadProgress} />
              </div>
            </CardContent>
          </Card>
        )}

        {/* Actions */}
        {files.length > 0 && !uploading && (
          <div className="flex gap-4">
            <Button onClick={handleUpload} className="flex-1">
              Upload {files.length} {files.length === 1 ? 'Image' : 'Images'} from {folderGroups.length} {folderGroups.length === 1 ? 'Folder' : 'Folders'}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setFiles([]);
                setFolderGroups([]);
              }}
            >
              Clear All
            </Button>
          </div>
        )}

        {/* Instructions */}
        <div className="mt-8 p-4 bg-muted/50 dark:bg-muted/30 rounded-lg">
          <h3 className="font-medium mb-2">How it works:</h3>
          <ul className="text-sm text-muted-foreground space-y-1">
            <li>• <strong>Upload:</strong> Organize images by folder - each folder becomes a book</li>
            <li>• <strong>Select Category:</strong> Choose an eBay category on the review page</li>
            <li>• <strong>AI Extraction:</strong> GPT-4o Vision analyzes your images and extracts category-specific book details</li>
            <li>• <strong>Review:</strong> Check and edit the AI-generated eBay title and description</li>
            <li>• <strong>Publish:</strong> One-click publish to eBay with your connected account</li>
          </ul>
          <h3 className="font-medium mt-4 mb-2">Tips for best results:</h3>
          <ul className="text-sm text-muted-foreground space-y-1">
            <li>• Include front cover, spine, back cover, and title/copyright pages</li>
            <li>• Capture clear photos of ISBN/barcode</li>
            <li>• Show any condition issues, signatures, or special features</li>
            <li>• Good lighting and focus help AI extract accurate details</li>
          </ul>
        </div>

        {/* OCR Capabilities */}
        {ocrCapabilities && (
          <div className="mt-4 p-4 bg-blue-50 dark:bg-blue-950/20 rounded-lg border border-blue-200 dark:border-blue-800">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-medium text-blue-900 dark:text-blue-100">OCR Capabilities</h3>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowOcrCapabilities(!showOcrCapabilities)}
                className="text-blue-700 dark:text-blue-300"
              >
                {showOcrCapabilities ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
            {showOcrCapabilities && (
              <div className="grid grid-cols-3 gap-2 text-sm">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${ocrCapabilities.tesseract ? 'bg-green-500' : 'bg-red-500'}`}></div>
                  <span className="text-blue-800 dark:text-blue-200">Tesseract OCR</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${ocrCapabilities.pyzbar ? 'bg-green-500' : 'bg-red-500'}`}></div>
                  <span className="text-blue-800 dark:text-blue-200">Barcode Scanner</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${ocrCapabilities.opencv ? 'bg-green-500' : 'bg-red-500'}`}></div>
                  <span className="text-blue-800 dark:text-blue-200">Image Processing</span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}