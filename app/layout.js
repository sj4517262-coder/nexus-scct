import "./globals.css";

export const metadata = {
  title: "NEXUS | Supply Chain Control Tower",
  description:
    "Monitor supply, manage logistics, and review operational decisions in one workspace.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
