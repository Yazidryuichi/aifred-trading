import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import bcrypt from "bcryptjs";

export const authOptions: NextAuthOptions = {
  providers: [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const email = process.env.AUTH_EMAIL;
        const passwordHash = process.env.AUTH_PASSWORD_HASH;

        if (!email || !passwordHash) {
          throw new Error("Auth not configured. Set AUTH_EMAIL and AUTH_PASSWORD_HASH env vars.");
        }

        if (
          credentials?.email === email &&
          bcrypt.compareSync(credentials.password, passwordHash)
        ) {
          return { id: "1", email, name: "AIFred Admin" };
        }

        return null;
      },
    }),
  ],
  session: {
    strategy: "jwt",
    maxAge: 24 * 60 * 60, // 24 hours
  },
  pages: {
    signIn: "/login",
  },
  secret: process.env.NEXTAUTH_SECRET || "aifred-dev-secret-change-in-prod",
};
