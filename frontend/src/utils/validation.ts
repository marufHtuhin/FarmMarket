import { z } from "zod";

export const loginSchema = z.object({
  email: z.string().min(1, "required").email("invalidEmail"),
  password: z.string().min(6, "minChars6"),
});

export type LoginForm = z.infer<typeof loginSchema>;

export const registerSchema = z
  .object({
    name: z.string().min(2, "required"),
    email: z.string().min(1, "required").email("invalidEmail"),
    phone: z.string().optional(),
    // Minimum 6 characters, any characters allowed — no letter/digit
    // complexity rule (matches the backend; user decision, 18 Nov 2026).
    password: z.string().min(6, "minChars6"),
    confirmPassword: z.string().min(6, "minChars6"),
    role: z.enum(["farmer", "buyer", "transporter"], { message: "required" }),
    // District is required (64-district select); upazila is optional and
    // depends on the chosen district.
    district: z.string().min(1, "required"),
    upazila: z.string().optional(),
    business_name: z.string().optional(),
  })
  .refine((d) => d.password === d.confirmPassword, {
    message: "passwordsMismatch",
    path: ["confirmPassword"],
  });

export type RegisterForm = z.infer<typeof registerSchema>;

export const listingSchema = z.object({
  name: z.string().min(1, "required"),
  quantity: z.number().positive("positiveNumber"),
  unit: z.enum(["kg", "quintal", "ton", "piece"]),
  price_per_unit: z.number().positive("positiveNumber"),
  district: z.string().min(1, "required"),
  harvest_date: z.string().optional(),
  available_until: z.string().optional(),
  description: z.string().optional(),
  image_url: z.string().optional(),
  farm_id: z.number().optional(),
});

export type ListingForm = z.infer<typeof listingSchema>;

export const farmSchema = z.object({
  name: z.string().min(1, "required"),
  district: z.string().min(1, "required"),
  upazila: z.string().optional(),
  area_acres: z.number().positive("positiveNumber").optional(),
  country_code: z.string().optional(),
});

export const demandSchema = z.object({
  product_name: z.string().min(1, "required"),
  required_quantity: z.number().positive("positiveNumber"),
  unit: z.enum(["kg", "quintal", "ton", "piece"]),
  target_price: z.number().positive("positiveNumber"),
  district: z.string().min(1, "required"),
  required_date: z.string().optional(),
  notes: z.string().optional(),
});
