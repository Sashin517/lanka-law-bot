"use client";

import { User } from "lucide-react";
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
      setError("Passwords do not match.");
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
    <div className="flex bg-background text-white flex-col items-center justify-center h-screen">
      <div className="bg-dark-blue p-8 rounded-lg w-full max-w-md">
        <div className="text-center mb-6">
          <h2 className="text-2xl font-serif tracking-wide">Sign up</h2>
          <p>Welcome to LankaLawBot</p>
        </div>

        <form onSubmit={handleEmailSignup} className="flex flex-col gap-4">
          {error && (
            <p className="text-sm text-red-400 bg-red-400/10 border border-red-400/30 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <label htmlFor="displayName">Display Name</label>
          <input
            id="displayName"
            type="text"
            placeholder="Display Name"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            required
            autoComplete="name"
            className="bg-light-blue p-2 rounded-lg"
          />

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
            minLength={6}
            autoComplete="new-password"
            className="bg-light-blue p-2 rounded-lg"
          />

          <label htmlFor="confirm-password">Confirm Password</label>
          <input
            id="confirm-password"
            type="password"
            placeholder="Confirm Password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
            minLength={6}
            autoComplete="new-password"
            className="bg-light-blue p-2 rounded-lg"
          />

          <button
            type="submit"
            disabled={loading}
            className="bg-yellow text-dark-blue p-2 rounded-lg disabled:opacity-60"
          >
            {loading ? "Creating account…" : "Sign up"}{" "}
            <User className="inline size-4" />
          </button>

          <p className="text-sm text-center">or</p>

          <button
            type="button"
            onClick={handleGoogleSignup}
            disabled={loading}
            className="bg-light-blue p-2 rounded-lg disabled:opacity-60"
          >
            Continue with Google
          </button>

          <p className="text-sm text-center">
            Already have an account?{" "}
            <Link href="/login" className="underline underline-offset-3">
              Log in here
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
