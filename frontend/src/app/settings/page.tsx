'use client';

import { useState, useEffect } from 'react';
import { aiSettingsApi, AISettings, UpdateAISettingsRequest } from '@/lib/api';
import { ebayOAuthApi, formatExpirationTime } from '@/lib/ebay';
import { useToast } from '@/hooks/use-toast';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Settings, Save, RotateCcw, Link as LinkIcon, CheckCircle, XCircle, RefreshCw, ExternalLink, Brain, Loader2 } from 'lucide-react';

export default function SettingsPage() {
  const { toast } = useToast();
  
  // eBay OAuth state
  const [oauthStatus, setOAuthStatus] = useState<any>(null);
  const [oauthLoading, setOAuthLoading] = useState(false);
  const [authCode, setAuthCode] = useState('');
  const [exchangingCode, setExchangingCode] = useState(false);
  const [manualToken, setManualToken] = useState('');
  const [settingManualToken, setSettingManualToken] = useState(false);
  
  // AI Settings state
  const [aiSettings, setAiSettings] = useState<AISettings | null>(null);
  const [aiSettingsLoading, setAiSettingsLoading] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [aiProvider, setAiProvider] = useState<'openai' | 'openrouter' | 'gemini'>('openai');
  const [openaiKey, setOpenaiKey] = useState('');
  const [openrouterKey, setOpenrouterKey] = useState('');
  const [geminiKey, setGeminiKey] = useState('');

  useEffect(() => {
    loadOAuthStatus();
    loadAISettings();
  }, []);
  
  // Refresh OAuth status every 30 seconds if connected
  useEffect(() => {
    if (oauthStatus?.connected) {
      const interval = setInterval(() => {
        loadOAuthStatus();
      }, 30000);
      return () => clearInterval(interval);
    }
  }, [oauthStatus?.connected]);

  // eBay OAuth functions
  const loadOAuthStatus = async () => {
    try {
      const status = await ebayOAuthApi.getStatus();
      setOAuthStatus(status);
    } catch (error: any) {
      console.error('Failed to load OAuth status:', error);
      if (error.message && error.message.includes('Backend server is not running')) {
        setOAuthStatus({ connected: false, error: 'Backend server is not running' });
      } else {
        setOAuthStatus({ connected: false, error: 'Failed to load status' });
      }
    }
  };

  const handleConnect = async () => {
    setOAuthLoading(true);
    try {
      const { auth_url } = await ebayOAuthApi.getAuthUrl();
      // Navigate to external URL
      window.location.href = auth_url;
    } catch (error: any) {
      toast({
        title: 'Failed to get authorization URL',
        description: error.message || 'Unknown error occurred',
        variant: 'destructive',
      });
      setOAuthLoading(false);
    }
  };

  const handleExchangeCode = async () => {
    if (!authCode.trim()) {
      toast({
        title: 'Authorization code required',
        description: 'Please paste the authorization code from eBay',
        variant: 'destructive',
      });
      return;
    }

    setExchangingCode(true);
    try {
      const result = await ebayOAuthApi.exchangeCode(authCode.trim());
      if (result.ok) {
        toast({
          title: 'Successfully connected to eBay',
          description: `Token expires in ${formatExpirationTime(result.expires_in)}`,
        });
        setAuthCode('');
        await loadOAuthStatus();
      } else {
        throw new Error('Exchange failed');
      }
    } catch (error: any) {
      toast({
        title: 'Failed to connect',
        description: error.message || 'Invalid authorization code or connection error',
        variant: 'destructive',
      });
    } finally {
      setExchangingCode(false);
    }
  };

  const handleSetManualToken = async () => {
    if (!manualToken.trim()) {
      toast({
        title: 'Token required',
        description: 'Please paste your User Token from eBay Developer Console',
        variant: 'destructive',
      });
      return;
    }

    setSettingManualToken(true);
    try {
      const result = await ebayOAuthApi.setManualToken(manualToken.trim());
      if (result.ok) {
        toast({
          title: 'Successfully connected to eBay',
          description: `Token expires in ${formatExpirationTime(result.expires_in)}`,
        });
        setManualToken('');
        await loadOAuthStatus();
      } else {
        throw new Error('Failed to save token');
      }
    } catch (error: any) {
      toast({
        title: 'Failed to connect',
        description: error.message || 'Invalid token or connection error',
        variant: 'destructive',
      });
    } finally {
      setSettingManualToken(false);
    }
  };

  const handleDisconnect = async () => {
    setOAuthLoading(true);
    try {
      await ebayOAuthApi.disconnect();
      toast({
        title: 'Disconnected from eBay',
        description: 'OAuth tokens have been removed',
      });
      await loadOAuthStatus();
    } catch (error: any) {
      toast({
        title: 'Failed to disconnect',
        description: error.message || 'Unknown error occurred',
        variant: 'destructive',
      });
    } finally {
      setOAuthLoading(false);
    }
  };

  const handleRefreshToken = async () => {
    setOAuthLoading(true);
    try {
      const result = await ebayOAuthApi.refreshToken();
      toast({
        title: 'Token refreshed',
        description: `New token expires in ${formatExpirationTime(result.expires_in)}`,
      });
      await loadOAuthStatus();
    } catch (error: any) {
      toast({
        title: 'Failed to refresh token',
        description: error.message || 'Unknown error occurred',
        variant: 'destructive',
      });
    } finally {
      setOAuthLoading(false);
    }
  };

  // AI Settings functions
  const loadAISettings = async () => {
    try {
      const settings = await aiSettingsApi.getSettings();
      setAiSettings(settings);
      setAiProvider(settings.provider);
      // Don't set keys - they're redacted
    } catch (error: any) {
      console.error('Failed to load AI settings:', error);
      if (error.message && error.message.includes('Backend server is not running')) {
        toast({
          title: 'Backend server not available',
          description: 'Please ensure the backend is running on http://127.0.0.1:8000',
          variant: 'destructive',
        });
      }
    }
  };

  const handleSaveAISettings = async () => {
    setAiSettingsLoading(true);
    try {
      const updateData: UpdateAISettingsRequest = {
        provider: aiProvider,
      };

      // Only include keys if they're provided (non-empty)
      if (openaiKey.trim()) {
        updateData.openai_api_key = openaiKey.trim();
      }
      if (openrouterKey.trim()) {
        updateData.openrouter_api_key = openrouterKey.trim();
      }
      if (geminiKey.trim()) {
        updateData.gemini_api_key = geminiKey.trim();
      }

      const updated = await aiSettingsApi.updateSettings(updateData);
      setAiSettings(updated);
      setOpenaiKey(''); // Clear input after save
      setOpenrouterKey('');
      setGeminiKey('');

      toast({
        title: 'AI settings saved',
        description: `Provider set to ${updated.provider}`,
      });
    } catch (error: any) {
      toast({
        title: 'Failed to save AI settings',
        description: error.message || 'Unknown error occurred',
        variant: 'destructive',
      });
    } finally {
      setAiSettingsLoading(false);
    }
  };

  const handleTestConnection = async () => {
    setTestingConnection(true);
    try {
      const result = await aiSettingsApi.testConnection();
      if (result.success) {
        toast({
          title: 'Connection test successful',
          description: result.message,
        });
      } else {
        toast({
          title: 'Connection test failed',
          description: result.message,
          variant: 'destructive',
        });
      }
    } catch (error: any) {
      toast({
        title: 'Connection test failed',
        description: error.message || 'Unknown error occurred',
        variant: 'destructive',
      });
    } finally {
      setTestingConnection(false);
    }
  };

  return (
    <div className="container mx-auto p-6">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-2 mb-6">
          <Settings className="h-6 w-6" />
          <h1 className="text-2xl font-bold">Settings</h1>
        </div>

        {/* AI Provider Settings */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Brain className="h-5 w-5" />
              AI Provider Settings
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              Configure your AI provider and API keys for vision extraction. Keys are encrypted when stored.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Provider Selection */}
            <div className="space-y-2">
              <Label htmlFor="ai_provider">AI Provider</Label>
              <Select value={aiProvider} onValueChange={(value: 'openai' | 'openrouter' | 'gemini') => setAiProvider(value)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="openai">OpenAI (GPT-4o / GPT-5)</SelectItem>
                  <SelectItem value="gemini">Google Gemini 2.5 Pro</SelectItem>
                  <SelectItem value="openrouter">OpenRouter (Multiple Models)</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {aiProvider === 'gemini' ? 'Gemini 2.5 Pro excels at vision tasks and document understanding.' :
                 aiProvider === 'openrouter' ? 'OpenRouter provides access to multiple AI models via one API.' :
                 'OpenAI provides GPT-4o and GPT-5 for vision extraction.'}
              </p>
            </div>

            {/* Current Settings Display */}
            {aiSettings && (
              <div className="p-4 bg-muted/50 rounded-lg space-y-2">
                <div className="text-sm">
                  <div className="font-medium">Current Configuration</div>
                  <div className="text-muted-foreground mt-1">
                    <div>Provider: <span className="font-mono">{aiSettings.provider}</span></div>
                    {aiSettings.openai_api_key && (
                      <div>OpenAI Key: <span className="font-mono">{aiSettings.openai_api_key}</span></div>
                    )}
                    {aiSettings.openrouter_api_key && (
                      <div>OpenRouter Key: <span className="font-mono">{aiSettings.openrouter_api_key}</span></div>
                    )}
                    {(aiSettings as any).gemini_api_key && (
                      <div>Gemini Key: <span className="font-mono">{(aiSettings as any).gemini_api_key}</span></div>
                    )}
                    <div className="mt-2 text-xs">Model: {
                      aiSettings.provider === 'openai' ? aiSettings.openai_model :
                      aiSettings.provider === 'gemini' ? (aiSettings as any).gemini_model || 'gemini-2.0-flash-exp' :
                      aiSettings.openrouter_model
                    }</div>
                  </div>
                </div>
              </div>
            )}

            {/* API Key Inputs */}
            <div className="space-y-4 pt-4 border-t">
              <div className="space-y-2">
                <Label htmlFor="openai_key">OpenAI API Key</Label>
                <Input
                  id="openai_key"
                  type="password"
                  value={openaiKey}
                  onChange={(e) => setOpenaiKey(e.target.value)}
                  placeholder="Enter new OpenAI API key (leave empty to keep current)"
                />
                <p className="text-xs text-muted-foreground">
                  Your OpenAI API key will be encrypted before storage.
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="gemini_key">Google Gemini API Key</Label>
                <Input
                  id="gemini_key"
                  type="password"
                  value={geminiKey}
                  onChange={(e) => setGeminiKey(e.target.value)}
                  placeholder="Enter new Gemini API key (leave empty to keep current)"
                />
                <p className="text-xs text-muted-foreground">
                  Get your Gemini API key from <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener noreferrer" className="underline">Google AI Studio</a>
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="openrouter_key">OpenRouter API Key</Label>
                <Input
                  id="openrouter_key"
                  type="password"
                  value={openrouterKey}
                  onChange={(e) => setOpenrouterKey(e.target.value)}
                  placeholder="Enter new OpenRouter API key (leave empty to keep current)"
                />
                <p className="text-xs text-muted-foreground">
                  Your OpenRouter API key will be encrypted before storage.
                </p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-2 pt-4 border-t">
              <Button
                onClick={handleSaveAISettings}
                disabled={aiSettingsLoading}
              >
                {aiSettingsLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4 mr-2" />
                    Save Settings
                  </>
                )}
              </Button>
              <Button
                variant="outline"
                onClick={handleTestConnection}
                disabled={testingConnection || !aiSettings}
              >
                {testingConnection ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Testing...
                  </>
                ) : (
                  <>
                    <CheckCircle className="h-4 w-4 mr-2" />
                    Test Connection
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* eBay OAuth Connection */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <LinkIcon className="h-5 w-5" />
              eBay Account Connection
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              Connect your eBay account to enable direct publishing of listings from the review page.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Connection Status */}
            <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
              <div className="flex items-center gap-3">
                {oauthStatus?.connected ? (
                  <>
                    <CheckCircle className="h-5 w-5 text-green-600" />
                    <div>
                      <div className="font-medium">Connected</div>
                      {oauthStatus.expires_in && (
                        <div className="text-sm text-muted-foreground">
                          Expires in {formatExpirationTime(oauthStatus.expires_in)}
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <XCircle className="h-5 w-5 text-red-600" />
                    <div>
                      <div className="font-medium">Not Connected</div>
                      {oauthStatus?.error && (
                        <div className="text-sm text-muted-foreground">{oauthStatus.error}</div>
                      )}
                    </div>
                  </>
                )}
              </div>
              {oauthStatus?.connected && (
                <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                  Active
                </Badge>
              )}
            </div>

            {/* Connection Actions */}
            {!oauthStatus?.connected ? (
              <div className="space-y-4">
                <div>
                  <Button
                    onClick={handleConnect}
                    disabled={oauthLoading}
                    className="w-full"
                  >
                    <LinkIcon className="h-4 w-4 mr-2" />
                    {oauthLoading ? 'Opening...' : 'Connect to eBay'}
                  </Button>
                </div>
                
                {/* Code Exchange */}
                <div className="space-y-2 pt-4 border-t">
                  <Label htmlFor="auth_code">Authorization Code</Label>
                  <div className="flex gap-2">
                    <Input
                      id="auth_code"
                      value={authCode}
                      onChange={(e) => setAuthCode(e.target.value)}
                      placeholder="Paste authorization code from eBay"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && authCode.trim()) {
                          handleExchangeCode();
                        }
                      }}
                    />
                    <Button
                      onClick={handleExchangeCode}
                      disabled={exchangingCode || !authCode.trim()}
                    >
                      {exchangingCode ? 'Connecting...' : 'Connect'}
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    After clicking "Connect to eBay", authorize the app and copy the code from the redirect URL.
                  </p>
                </div>
                
                {/* Manual Token Entry */}
                <div className="space-y-2 pt-4 border-t">
                  <Label htmlFor="manual_token">Or Enter User Token Manually</Label>
                  <p className="text-xs text-muted-foreground mb-2">
                    If you have a User Token from eBay Developer Console, paste it here to bypass OAuth.
                  </p>
                  <div className="flex gap-2">
                    <Input
                      id="manual_token"
                      type="password"
                      value={manualToken}
                      onChange={(e) => setManualToken(e.target.value)}
                      placeholder="Paste User Token from eBay Developer Console"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && manualToken.trim()) {
                          handleSetManualToken();
                        }
                      }}
                    />
                    <Button
                      onClick={handleSetManualToken}
                      disabled={settingManualToken || !manualToken.trim()}
                    >
                      {settingManualToken ? 'Connecting...' : 'Connect'}
                    </Button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={handleRefreshToken}
                  disabled={oauthLoading}
                >
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Refresh Token
                </Button>
                <Button
                  variant="destructive"
                  onClick={handleDisconnect}
                  disabled={oauthLoading}
                >
                  <XCircle className="h-4 w-4 mr-2" />
                  Disconnect
                </Button>
              </div>
            )}

            {/* Connection Info */}
            {oauthStatus?.connected && oauthStatus.scope && (
              <div className="pt-4 border-t">
                <div className="text-sm">
                  <div className="font-medium mb-1">Scopes:</div>
                  <div className="text-muted-foreground text-xs font-mono bg-muted p-2 rounded">
                    {oauthStatus.scope}
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Application Settings */}
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Application Settings</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4 text-sm">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium">AI Provider</h4>
                  <p className="text-muted-foreground">Currently using mock mode</p>
                </div>
                <Badge variant="outline">Mock</Badge>
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium">Database</h4>
                  <p className="text-muted-foreground">Local SQLite database</p>
                </div>
                <Badge variant="outline">Local</Badge>
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium">Image Storage</h4>
                  <p className="text-muted-foreground">Local filesystem</p>
                </div>
                <Badge variant="outline">Local</Badge>
              </div>
            </div>
            <div className="mt-4 p-3 bg-muted/50 rounded text-xs text-muted-foreground">
              <strong>Note:</strong> This application runs entirely locally. No data is sent to external servers except when configured with external AI providers or metadata services.
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}