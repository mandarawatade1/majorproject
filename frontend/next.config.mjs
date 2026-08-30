/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The portal renders on the server and talks to FastAPI over the container
  // network, so no API routes are proxied and no images are optimised through
  // a remote loader. Keeping both off means the build has no network
  // dependency beyond npm install.
  images: { unoptimized: true },
};

export default nextConfig;
