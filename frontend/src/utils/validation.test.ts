import { describe, expect, it } from "vitest";
import { listingSchema, loginSchema, registerSchema } from "../utils/validation";

describe("loginSchema", () => {
  it("rejects an invalid email and a short password", () => {
    const res = loginSchema.safeParse({ email: "not-an-email", password: "123" });
    expect(res.success).toBe(false);
    if (!res.success) {
      const paths = res.error.issues.map((i) => i.path[0]);
      expect(paths).toContain("email");
      expect(paths).toContain("password");
    }
  });

  it("accepts valid credentials", () => {
    expect(loginSchema.safeParse({ email: "farmer@farmmarket.demo", password: "Demo123!" }).success).toBe(true);
  });
});

describe("registerSchema", () => {
  const base = {
    name: "Test User",
    email: "test@example.com",
    password: "secret1",
    confirmPassword: "secret1",
    role: "transporter" as const,
  };

  it("accepts farmer, buyer and transporter roles", () => {
    for (const role of ["farmer", "buyer", "transporter"] as const) {
      expect(registerSchema.safeParse({ ...base, role }).success).toBe(true);
    }
  });

  it("rejects the admin role and mismatched passwords", () => {
    expect(registerSchema.safeParse({ ...base, role: "admin" }).success).toBe(false);
    const res = registerSchema.safeParse({ ...base, confirmPassword: "different" });
    expect(res.success).toBe(false);
    if (!res.success) {
      expect(res.error.issues[0].message).toBe("passwordsMismatch");
    }
  });
});

describe("listingSchema", () => {
  const base = {
    name: "Tomato",
    quantity: 10,
    unit: "kg" as const,
    price_per_unit: 38,
    district: "Dhaka",
  };

  it("rejects zero or negative quantity and price", () => {
    expect(listingSchema.safeParse({ ...base, quantity: 0 }).success).toBe(false);
    expect(listingSchema.safeParse({ ...base, quantity: -5 }).success).toBe(false);
    expect(listingSchema.safeParse({ ...base, price_per_unit: 0 }).success).toBe(false);
  });

  it("accepts a valid listing", () => {
    expect(listingSchema.safeParse(base).success).toBe(true);
  });
});
