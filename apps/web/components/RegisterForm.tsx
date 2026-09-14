"use client";
import {FormEvent,useState} from "react";
import {useRouter} from "next/navigation";

function detail(value:unknown){if(typeof value==="string")return value;if(Array.isArray(value))return value.map((item:{msg?:string})=>item.msg||"Invalid input").join("; ");return "Registration failed."}

export default function RegisterForm({division}:{division:"it"|"overseas"}){
  const router=useRouter();const[busy,setBusy]=useState(false);const[message,setMessage]=useState("");
  async function submit(event:FormEvent<HTMLFormElement>){event.preventDefault();setBusy(true);setMessage("");const form=new FormData(event.currentTarget);const response=await fetch("/api/v1/auth/register",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({full_name:form.get("full_name"),email:form.get("email"),phone:form.get("phone")||null,password:form.get("password"),division,account_type:form.get("account_type")||"student"})});const data=await response.json().catch(()=>({}));setBusy(false);if(!response.ok){setMessage(detail(data.detail));return}router.push(data.user.role==="agent"?"/overseas/agent/dashboard":division==="it"?"/it/student/dashboard":"/overseas/student/dashboard");router.refresh()}
  return <form className="form" onSubmit={submit}><div className="field"><label>Full name</label><input name="full_name" autoComplete="name" required/></div><div className="field"><label>Email</label><input name="email" type="email" autoComplete="email" required/></div><div className="field"><label>Phone</label><input name="phone" type="tel" autoComplete="tel"/></div>{division==="overseas"&&<div className="field"><label>Account type</label><select name="account_type" defaultValue="student"><option value="student">Student</option><option value="agent">Education agent</option></select></div>}<div className="field"><label>Password</label><input name="password" type="password" minLength={10} autoComplete="new-password" required/><span className="muted" style={{fontSize:12}}>Use at least 10 characters.</span></div>{message&&<div className="form-error">{message}</div>}<button className="btn" disabled={busy}>{busy?"Creating account…":"Create account"}</button></form>
}
