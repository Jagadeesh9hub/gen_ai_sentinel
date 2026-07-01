import "./globals.css";

export const metadata = {
  title: "SENTINEL — Public Safety Decision Intelligence",
  description: "Situational Event iNTELligence",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
