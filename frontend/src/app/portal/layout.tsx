export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen bg-gray-50">
          <header className="bg-white border-b px-6 py-4 flex items-center gap-3">
            <div className="font-bold text-lg">AP Vendor Portal</div>
          </header>
          <main className="container mx-auto py-8 px-4">{children}</main>
        </div>
      </body>
    </html>
  );
}
