import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Student Advisory",
  description: "Synthetic local advisory foundation",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip" href="#main">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
