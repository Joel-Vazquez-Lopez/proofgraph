/** @type {import('next').NextConfig} */
const nextConfig = {
  distDir: process.env.PROOFGRAPH_E2E === '1' ? '.next-e2e' : '.next',
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: `http://127.0.0.1:${process.env.PROOFGRAPH_API_PORT || '8000'}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
