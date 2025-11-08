"""
Tests for eBay Media API client
"""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from integrations.ebay.media_api import (
    upload_from_file,
    upload_many,
    health_check,
    MediaAPIError,
    EbayMediaUploadError,
    MediaAPIAuthenticationError,
    MediaAPIRateLimitError,
    MediaAPIValidationError
)


class TestMediaAPIUpload:
    """Test Media API upload functions"""
    
    @pytest.fixture
    def mock_image_path(self, tmp_path):
        """Create a mock image file"""
        image_file = tmp_path / "test.jpg"
        image_file.write_bytes(b"fake image data")
        return image_file
    
    @pytest.fixture
    def mock_token(self):
        """Mock OAuth token"""
        return "mock_access_token"
    
    @pytest.mark.asyncio
    async def test_upload_from_file_success(self, mock_image_path, mock_token):
        """Test successful image upload"""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "imageUrl": "https://i.ebayimg.com/images/g/ABC123/image.jpg"
        }
        mock_response.headers.get.return_value = None
        
        with patch('integrations.ebay.media_api.httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.return_value = mock_response
            
            eps_url = await upload_from_file(mock_image_path, mock_token)
            
            assert eps_url == "https://i.ebayimg.com/images/g/ABC123/image.jpg"
            mock_instance.post.assert_called_once()
            call_args = mock_instance.post.call_args
            assert call_args[0][0] == "https://api.ebay.com/commerce/media/v1/image"
            assert 'Authorization' in call_args[1]['headers']
            assert call_args[1]['headers']['Authorization'] == f"Bearer {mock_token}"
            assert 'X-EBAY-C-MARKETPLACE-ID' in call_args[1]['headers']
    
    @pytest.mark.asyncio
    async def test_upload_from_file_authentication_error(self, mock_image_path, mock_token):
        """Test 401 authentication error"""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.headers.get.return_value = None
        
        with patch('integrations.ebay.media_api.httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.side_effect = httpx.HTTPStatusError(
                "Unauthorized",
                request=MagicMock(),
                response=mock_response
            )
            
            with pytest.raises(EbayMediaUploadError) as exc_info:
                await upload_from_file(mock_image_path, mock_token)
            
            assert exc_info.value.status_code == 401
    
    @pytest.mark.asyncio
    async def test_upload_from_file_rate_limit_retry(self, mock_image_path, mock_token):
        """Test 429 rate limit with retry"""
        # First attempt: rate limited
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        mock_response_429.headers.get.return_value = "2"
        
        # Second attempt: success
        mock_response_201 = MagicMock()
        mock_response_201.status_code = 201
        mock_response_201.json.return_value = {
            "imageUrl": "https://i.ebayimg.com/images/g/ABC123/image.jpg"
        }
        mock_response_201.headers.get.return_value = None
        
        with patch('integrations.ebay.media_api.httpx.AsyncClient') as mock_client, \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.side_effect = [mock_response_429, mock_response_201]
            
            eps_url = await upload_from_file(mock_image_path, mock_token)
            
            assert eps_url == "https://i.ebayimg.com/images/g/ABC123/image.jpg"
            assert mock_instance.post.call_count == 2
            mock_sleep.assert_called()
    
    @pytest.mark.asyncio
    async def test_upload_from_file_validation_error(self, mock_image_path, mock_token):
        """Test 400 validation error"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"errors": [{"message": "Invalid image format"}]}'
        mock_response.json.return_value = {
            "errors": [{"message": "Invalid image format"}]
        }
        mock_response.headers.get.return_value = None
        mock_response.headers = {}
        
        with patch('integrations.ebay.media_api.httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.side_effect = httpx.HTTPStatusError(
                "Bad Request",
                request=MagicMock(),
                response=mock_response
            )
            
            with pytest.raises(EbayMediaUploadError) as exc_info:
                await upload_from_file(mock_image_path, mock_token)
            
            assert exc_info.value.status_code == 400
            assert "Invalid image format" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_upload_from_file_5xx_retry(self, mock_image_path, mock_token):
        """Test 5xx error with retry"""
        # First attempt: server error
        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500
        mock_response_500.headers.get.return_value = None
        
        # Second attempt: success
        mock_response_201 = MagicMock()
        mock_response_201.status_code = 201
        mock_response_201.json.return_value = {
            "imageUrl": "https://i.ebayimg.com/images/g/ABC123/image.jpg"
        }
        mock_response_201.headers.get.return_value = None
        
        with patch('integrations.ebay.media_api.httpx.AsyncClient') as mock_client, \
             patch('integrations.ebay.media_api._backoff', new_callable=AsyncMock) as mock_backoff:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.side_effect = [mock_response_500, mock_response_201]
            
            eps_url = await upload_from_file(mock_image_path, mock_token)
            
            assert eps_url == "https://i.ebayimg.com/images/g/ABC123/image.jpg"
            assert mock_instance.post.call_count == 2
            mock_backoff.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_from_file_request_id_in_logs(self, mock_image_path, mock_token):
        """Test that request-id is extracted from response headers"""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "imageId": "v1|123456|0",
            "imageUrl": "https://i.ebayimg.com/images/g/ABC123/image.jpg"
        }
        mock_response.headers = {
            'X-EBAY-C-REQUEST-ID': 'test-request-id-123'
        }
        mock_response.headers.get = lambda key, default=None: mock_response.headers.get(key, default)
        
        with patch('integrations.ebay.media_api.httpx.AsyncClient') as mock_client, \
             patch('integrations.ebay.media_api.logger') as mock_logger:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.return_value = mock_response
            
            await upload_from_file(mock_image_path, mock_token)
            
            # Verify request-id is passed to logger
            mock_logger.info.assert_called()
            call_kwargs = mock_logger.info.call_args[1]
            assert call_kwargs.get('extra', {}).get('request_id') == 'test-request-id-123'
    
    @pytest.mark.asyncio
    async def test_upload_many_success(self, tmp_path, mock_token):
        """Test uploading multiple images"""
        image_paths = []
        for i in range(3):
            img = tmp_path / f"test_{i}.jpg"
            img.write_bytes(b"fake image data")
            image_paths.append(img)
        
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.headers.get.return_value = None
        
        with patch('integrations.ebay.media_api.upload_from_file') as mock_upload:
            mock_upload.side_effect = [
                "https://i.ebayimg.com/images/g/img1.jpg",
                "https://i.ebayimg.com/images/g/img2.jpg",
                "https://i.ebayimg.com/images/g/img3.jpg"
            ]
            
            eps_urls = await upload_many(image_paths, mock_token)
            
            assert len(eps_urls) == 3
            assert all(url.startswith('https://') for url in eps_urls)
            assert mock_upload.call_count == 3
    
    @pytest.mark.asyncio
    async def test_upload_many_too_many_images(self, tmp_path, mock_token):
        """Test that too many images raises ValueError"""
        # Create 25 images (max is 24)
        image_paths = []
        for i in range(25):
            img = tmp_path / f"test_{i}.jpg"
            img.write_bytes(b"fake image data")
            image_paths.append(img)
        
        with pytest.raises(ValueError) as exc_info:
            await upload_many(image_paths, mock_token)
        
        assert "Too many images" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_upload_many_empty_list(self, mock_token):
        """Test that empty list raises ValueError"""
        with pytest.raises(ValueError) as exc_info:
            await upload_many([], mock_token)
        
        assert "Empty image list" in str(exc_info.value)
    
    def test_upload_from_file_invalid_path(self, mock_token):
        """Test that invalid file path raises ValueError"""
        fake_path = Path("/nonexistent/image.jpg")
        
        with pytest.raises(ValueError):
            import asyncio
            asyncio.run(upload_from_file(fake_path, mock_token))
    
    @pytest.mark.asyncio
    async def test_upload_from_file_404_error(self, mock_image_path, mock_token):
        """Test that 404 errors provide detailed context"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.headers = {'X-EBAY-C-REQUEST-ID': 'req-123'}
        mock_response.headers.get = lambda key, default=None: mock_response.headers.get(key, default)
        
        with patch('integrations.ebay.media_api.httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.side_effect = httpx.HTTPStatusError(
                "Not Found",
                request=MagicMock(),
                response=mock_response
            )
            
            with pytest.raises(EbayMediaUploadError) as exc_info:
                await upload_from_file(mock_image_path, mock_token)
            
            assert exc_info.value.status_code == 404
            assert exc_info.value.filename == mock_image_path.name
            assert exc_info.value.request_id == 'req-123'
            assert "404" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_upload_from_file_imageid_response(self, mock_image_path, mock_token):
        """Test handling response with both imageId and imageUrl"""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "imageId": "v1|1234567890|0",
            "imageUrl": "https://i.ebayimg.com/images/g/ABC123/image.jpg",
            "expirationDate": "2025-12-31T23:59:59Z"
        }
        mock_response.headers = {}
        mock_response.headers.get = lambda key, default=None: mock_response.headers.get(key, default)
        
        with patch('integrations.ebay.media_api.httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.return_value = mock_response
            
            eps_url = await upload_from_file(mock_image_path, mock_token)
            
            assert eps_url == "https://i.ebayimg.com/images/g/ABC123/image.jpg"
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_token):
        """Test health check returns True for accessible endpoint"""
        mock_response = MagicMock()
        mock_response.status_code = 405  # Method not allowed means endpoint exists
        mock_response.headers = {}
        mock_response.headers.get = lambda key, default=None: mock_response.headers.get(key, default)
        
        with patch('integrations.ebay.media_api.httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.head.return_value = mock_response
            
            result = await health_check(mock_token)
            
            assert result is True
            mock_instance.head.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_check_404_failure(self, mock_token):
        """Test health check returns False for 404"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.headers = {}
        mock_response.headers.get = lambda key, default=None: mock_response.headers.get(key, default)
        
        with patch('integrations.ebay.media_api.httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.head.return_value = mock_response
            
            result = await health_check(mock_token)
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_upload_many_health_check(self, tmp_path, mock_token):
        """Test that upload_many performs health check before batch upload"""
        image_paths = [tmp_path / f"test_{i}.jpg" for i in range(2)]
        for img in image_paths:
            img.write_bytes(b"fake image data")
        
        with patch('integrations.ebay.media_api.health_check') as mock_health, \
             patch('integrations.ebay.media_api.upload_from_file') as mock_upload:
            mock_health.return_value = True
            mock_upload.side_effect = [
                "https://i.ebayimg.com/images/g/img1.jpg",
                "https://i.ebayimg.com/images/g/img2.jpg"
            ]
            
            eps_urls = await upload_many(image_paths, mock_token, skip_health_check=False)
            
            mock_health.assert_called_once_with(mock_token, None)
            assert len(eps_urls) == 2

