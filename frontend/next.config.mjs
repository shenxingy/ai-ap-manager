/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required for standalone Docker builds (copies only necessary files)
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  // Allow dev server access from Tailscale and local network IPs
  allowedDevOrigins: [
    "100.0.0.0/8",       // All Tailscale IPs (100.x.x.x range)
    "192.168.0.0/16",    // Local network
    "10.0.0.0/8",        // Local network
  ],
};

export default nextConfig;
