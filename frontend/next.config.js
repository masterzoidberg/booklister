/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "i.ebayimg.com" },
      { protocol: "https", hostname: "covers.openlibrary.org" },
      { protocol: "https", hostname: "images-na.ssl-images-amazon.com" },
      { protocol: "https", hostname: "m.media-amazon.com" },
      // If you serve images from your own HTTPS domain/tunnel, add it here:
      // { protocol: "https", hostname: "your-domain.example.com" },
      // Local dev patterns are intentionally omitted for security. Prefer next/image with local paths.
    ],
  },
}

module.exports = nextConfig