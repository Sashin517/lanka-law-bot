"use client";

import { UserPlus, User, AlertCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import {
  getAuthErrorMessage,
  signInWithGoogle,
  signUpWithEmail,
} from "@/lib/firebase/auth";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleEmailSignup = async (event: FormEvent) => {
    event.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match. Please try again.");
      return;
    }

    setLoading(true);

    try {
      await signUpWithEmail(email, password, displayName);
      router.push("/");
    } catch (err) {
      setError(getAuthErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignup = async () => {
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
            Create an Account
          </h2>
          <p className="mt-2 text-sm text-slate-400">
            Join LankaLawBot to start your legal research
          </p>
        </div>

        {/* Error State */}
        {error && (
          <div className="flex items-center gap-3 rounded-lg bg-red-900/30 border border-red-500/50 p-4 text-sm text-red-200 animate-in fade-in slide-in-from-top-2">
            <AlertCircle className="h-5 w-5 text-red-400 shrink-0" />
            <p>{error}</p>
          </div>
        )}

        <form onSubmit={handleEmailSignup} className="mt-8 space-y-5">
          <div className="space-y-4">
            
            {/* Display Name Input */}
            <div>
              <label htmlFor="displayName" className="block text-sm font-medium text-slate-300 mb-1">
                Display Name
              </label>
              <input
                id="displayName"
                type="text"
                placeholder="John Doe"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                required
                autoComplete="name"
                className="block w-full rounded-lg border border-light-blue bg-background/50 px-4 py-3 text-slate-100 transition-all placeholder:text-slate-500 hover:border-light-blue/80 focus:border-yellow focus:bg-background focus:outline-none focus:ring-2 focus:ring-yellow/50"
              />
            </div>

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

            {/* Password Grid */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-slate-300 mb-1">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  minLength={6}
                  autoComplete="new-password"
                  className="block w-full rounded-lg border border-light-blue bg-background/50 px-4 py-3 text-slate-100 transition-all placeholder:text-slate-500 hover:border-light-blue/80 focus:border-yellow focus:bg-background focus:outline-none focus:ring-2 focus:ring-yellow/50"
                />
              </div>

              <div>
                <label htmlFor="confirm-password" className="block text-sm font-medium text-slate-300 mb-1">
                  Confirm
                </label>
                <input
                  id="confirm-password"
                  type="password"
                  placeholder="••••••••"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  required
                  minLength={6}
                  autoComplete="new-password"
                  className="block w-full rounded-lg border border-light-blue bg-background/50 px-4 py-3 text-slate-100 transition-all placeholder:text-slate-500 hover:border-light-blue/80 focus:border-yellow focus:bg-background focus:outline-none focus:ring-2 focus:ring-yellow/50"
                />
              </div>
            </div>
          </div>

          {/* Primary Action Button */}
          <button
            type="submit"
            disabled={loading}
            className="group flex w-full items-center justify-center gap-2 rounded-lg bg-yellow px-4 py-3 text-sm font-bold text-dark-blue shadow-sm transition-all hover:bg-yellow/90 focus:outline-none focus:ring-2 focus:ring-yellow focus:ring-offset-2 focus:ring-offset-background disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]"
          >
            {loading ? "Creating account…" : "Sign Up"}
            <UserPlus className="h-4 w-4 transition-transform group-hover:scale-110" />
          </button>

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-light-blue/30" />
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="bg-dark-blue px-4 text-slate-400">Or sign up with</span>
            </div>
          </div>

          {/* Secondary Action Button */}
          <button
            type="button"
            onClick={handleGoogleSignup}
            disabled={loading}
            className="flex w-full items-center justify-center gap-3 rounded-lg border border-light-blue bg-transparent px-4 py-3 text-sm font-medium text-slate-200 transition-all hover:bg-light-blue/20 focus:outline-none focus:ring-2 focus:ring-yellow focus:ring-offset-2 focus:ring-offset-background disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]"
          >
            <User className="h-4 w-4 text-slate-300" />
            Google Account
          </button>
        </form>

        {/* Footer */}
        <p className="mt-8 text-center text-sm text-slate-400">
          Already have an account?{" "}
          <Link href="/login" className="font-semibold text-yellow hover:text-yellow/80 transition-colors">
            Log in here
          </Link>
        </p>
      </div>
    </div>
  );
}