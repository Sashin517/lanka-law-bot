"use client";

import { LogIn } from "lucide-react";
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
    <div className="flex bg-background text-white flex-col items-center justify-center h-screen">
      <div className="bg-dark-blue p-8 rounded-lg w-full max-w-md">
        <div className="text-center mb-6">
          <h2 className="text-2xl font-serif tracking-wide">Login</h2>
          <p>Welcome to LankaLawBot</p>
        </div>

        <form onSubmit={handleEmailLogin} className="flex flex-col gap-4">
          {error && (
            <p className="text-sm text-red-400 bg-red-400/10 border border-red-400/30 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            placeholder="Email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            autoComplete="email"
            className="bg-light-blue p-2 rounded-lg"
          />

          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            placeholder="Password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            autoComplete="current-password"
            className="bg-light-blue p-2 rounded-lg"
          />

          <p className="text-sm text-center">
            Forgot password?{" "}
            <Link
              href="/forgot-password"
              className="underline underline-offset-3"
            >
              Click here
            </Link>
          </p>

          <button
            type="submit"
            disabled={loading}
            className="bg-yellow text-dark-blue p-2 rounded-lg disabled:opacity-60"
          >
            {loading ? "Signing in…" : "Login"}{" "}
            <LogIn className="inline size-4" />
          </button>

          <p className="text-sm text-center">or</p>

          <button
            type="button"
            onClick={handleGoogleLogin}
            disabled={loading}
            className="bg-light-blue p-2 rounded-lg disabled:opacity-60"
          >
            Continue with Google
          </button>

          <p className="text-sm text-center">
            Don&apos;t have an account?{" "}
            <Link href="/signup" className="underline underline-offset-3">
              Sign up here
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
