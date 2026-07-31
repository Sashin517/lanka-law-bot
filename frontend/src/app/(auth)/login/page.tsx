"use client";

import { LogIn, User, AlertCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import {
  getAuthErrorMessage,
  signInWithEmail,
  signInWithGoogle,
} from "@/lib/firebase/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleEmailLogin = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      await signInWithEmail(email, password);
      router.push("/");
    } catch (err) {
      setError(getAuthErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    setError("");
    setLoading(true);

    try {
      await signInWithGoogle();
      router.push("/");
    } catch (err) {
      setError(getAuthErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4 py-12 font-sans sm:px-6 lg:px-8">
      {/* Surface Card */}
      <div className="w-full max-w-md space-y-8 rounded-2xl bg-dark-blue p-10 shadow-2xl border border-light-blue/20">
        
        {/* Header Section */}
        <div className="text-center">
          <h2 className="mt-6 text-3xl font-serif tracking-tight text-slate-100">
            Welcome Back
          </h2>
          <p className="mt-2 text-sm text-slate-400">
            Sign in to access LankaLawBot
          </p>
        </div>

        {/* Error State */}
        {error && (
          <div className="flex items-center gap-3 rounded-lg bg-red-900/30 border border-red-500/50 p-4 text-sm text-red-200 animate-in fade-in slide-in-from-top-2">
            <AlertCircle className="h-5 w-5 text-red-400 shrink-0" />
            <p>{error}</p>
          </div>
        )}

        <form onSubmit={handleEmailLogin} className="mt-8 space-y-6">
          <div className="space-y-4">
            
            {/* Email Input */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-slate-300 mb-1">
                Email Address
              </label>
              <input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoComplete="email"
                className="block w-full rounded-lg border border-light-blue bg-background/50 px-4 py-3 text-slate-100 transition-all placeholder:text-slate-500 hover:border-light-blue/80 focus:border-yellow focus:bg-background focus:outline-none focus:ring-2 focus:ring-yellow/50"
              />
            </div>

            {/* Password Input */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label htmlFor="password" className="block text-sm font-medium text-slate-300">
                  Password
                </label>
                <Link href="/forgot-password" className="text-sm font-medium text-yellow hover:text-yellow/80 transition-colors">
                  Forgot password?
                </Link>
              </div>
              <input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                autoComplete="current-password"
                className="block w-full rounded-lg border border-light-blue bg-background/50 px-4 py-3 text-slate-100 transition-all placeholder:text-slate-500 hover:border-light-blue/80 focus:border-yellow focus:bg-background focus:outline-none focus:ring-2 focus:ring-yellow/50"
              />
            </div>
          </div>

          {/* Primary Action Button */}
          <button
            type="submit"
            disabled={loading}
            className="group flex w-full items-center justify-center gap-2 rounded-lg bg-yellow px-4 py-3 text-sm font-bold text-dark-blue shadow-sm transition-all hover:bg-yellow/90 focus:outline-none focus:ring-2 focus:ring-yellow focus:ring-offset-2 focus:ring-offset-background disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]"
          >
            {loading ? "Signing in…" : "Sign In"}
            <LogIn className="h-4 w-4 transition-transform group-hover:translate-x-1" />
          </button>

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-light-blue/30" />
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="bg-dark-blue px-4 text-slate-400">Or continue with</span>
            </div>
          </div>

          {/* Secondary Action Button (Ghost style for dark mode) */}
          <button
            type="button"
            onClick={handleGoogleLogin}
            disabled={loading}
            className="flex w-full items-center justify-center gap-3 rounded-lg border border-light-blue bg-transparent px-4 py-3 text-sm font-medium text-slate-200 transition-all hover:bg-light-blue/20 focus:outline-none focus:ring-2 focus:ring-yellow focus:ring-offset-2 focus:ring-offset-background disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]"
          >
            <User className="h-4 w-4 text-slate-300" />
            Google Account
          </button>
        </form>

        {/* Footer */}
        <p className="mt-8 text-center text-sm text-slate-400">
          Don&apos;t have an account?{" "}
          <Link href="/signup" className="font-semibold text-yellow hover:text-yellow/80 transition-colors">
            Sign up here
          </Link>
        </p>
      </div>
    </div>
  );
}