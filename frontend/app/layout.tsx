import "./globals.css";import Nav from "@/components/Nav";import AuthProvider from "@/components/AuthProvider";
export const metadata={title:"QuantForge AI",description:"Hybrid AI quantitative assessment platform"};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body className="grid-bg min-h-screen"><AuthProvider><Nav/>{children}</AuthProvider></body></html>}
