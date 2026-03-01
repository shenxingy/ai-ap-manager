/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required for standalone Docker builds (copies only necessary files)
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
};

export default nextConfig;
