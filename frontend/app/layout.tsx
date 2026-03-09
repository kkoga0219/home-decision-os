import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Home Decision OS",
  description: "住宅購入の意思決定エンジン",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>
        {/* ── Navigation ── */}
        <nav className="bg-white border-b border-gray-200 sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-14">
              <Link href="/" className="flex items-center gap-2 font-bold text-lg text-primary-700">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955a1.126 1.126 0 011.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
                </svg>
                Home Decision OS
              </Link>
              <div className="flex items-center gap-4">
                <Link href="/" className="text-sm text-gray-600 hover:text-primary-600 transition-colors">
                  物件一覧
                </Link>
                <Link href="/properties/new" className="text-sm text-gray-600 hover:text-primary-600 transition-colors">
                  物件登録
                </Link>
                <Link href="/comparison" className="text-sm text-gray-600 hover:text-primary-600 transition-colors">
                  比較
                </Link>
              </div>
            </div>
          </div>
        </nav>

        {/* ── Main ── */}
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
