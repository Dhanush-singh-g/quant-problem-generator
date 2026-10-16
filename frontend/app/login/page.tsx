"use client";
import {FormEvent,useEffect,useRef,useState} from "react";
import {googleLogin,login} from "@/lib/api";
import Link from "next/link";
import {useRouter} from "next/navigation";

declare global { interface Window { google?: any } }

export default function Login(){
 const [email,setEmail]=useState(""); const [password,setPassword]=useState(""); const [error,setError]=useState("");
 const router=useRouter(); const [busy,setBusy]=useState(false); const googleRef=useRef<HTMLDivElement>(null);
 async function finish(p:Promise<any>){setBusy(true);try{setError("");await p;router.push("/quiz")}catch(e:any){setError(e.message||"Sign in failed")}finally{setBusy(false)}}
 async function go(e:FormEvent){e.preventDefault();if(busy)return;await finish(login(email,password))}
 useEffect(()=>{
   const clientId=process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID; if(!clientId) return;
   const init=()=>{ if(!window.google||!googleRef.current)return; window.google.accounts.id.initialize({client_id:clientId,callback:(r:any)=>finish(googleLogin(r.credential))}); window.google.accounts.id.renderButton(googleRef.current,{theme:"outline",size:"large",width:360,text:"continue_with"}); };
   const existing=document.querySelector('script[data-qf-google]') as HTMLScriptElement|null; if(existing){init();existing.addEventListener("load",init);return()=>existing.removeEventListener("load",init);}
   const script=document.createElement("script"); script.src="https://accounts.google.com/gsi/client"; script.async=true; script.defer=true; script.dataset.qfGoogle="1"; script.onload=init; document.head.appendChild(script);return()=>{script.onload=null};
 },[]);
 return <main className="mx-auto max-w-md px-6 py-20"><div className="glass rounded-3xl p-8"><p className="text-sm font-bold uppercase tracking-widest text-cyan-400">Account</p><h1 className="mt-2 text-4xl font-black">Sign in</h1>
 <div ref={googleRef} className="mt-8 flex justify-center"/>
 {process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID&&<div className="my-6 flex items-center gap-3 text-xs text-slate-500"><span className="h-px flex-1 bg-white/10"/>OR<span className="h-px flex-1 bg-white/10"/></div>}
 <form onSubmit={go} className="space-y-4"><input className="w-full rounded-xl border border-white/10 bg-white/5 p-4" aria-label="Email" autoComplete="email" placeholder="Email" type="email" value={email} onChange={e=>setEmail(e.target.value)} required/><input className="w-full rounded-xl border border-white/10 bg-white/5 p-4" aria-label="Password" autoComplete="current-password" placeholder="Password" type="password" maxLength={128} value={password} onChange={e=>setPassword(e.target.value)} required/><button disabled={busy} className="w-full rounded-xl bg-cyan-400 p-4 font-bold text-black disabled:opacity-50">{busy?"Signing in…":"Sign in"}</button></form>{error&&<p role="alert" className="mt-4 text-sm text-red-400">{error}</p>}<p className="mt-6 text-sm text-slate-400">No account? <Link className="text-cyan-400" href="/register">Create one</Link></p></div></main>
}
