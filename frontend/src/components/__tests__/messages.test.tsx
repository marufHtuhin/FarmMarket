import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { Route, Routes, useLocation } from "react-router-dom";
import { renderWithProviders } from "../../test/test-utils";
import { MessagesPage } from "../../pages/Messages";
import { MessageButton } from "../MessageButton";

// Mock only the conversations API; everything else stays real.
vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/api")>();
  return {
    ...actual,
    conversationsApi: {
      list: vi.fn(),
      create: vi.fn(),
      unreadCount: vi.fn(),
      getMessages: vi.fn(),
      sendMessage: vi.fn(),
      markRead: vi.fn(),
    },
  };
});

import { conversationsApi, USER_KEY } from "../../services/api";

const mocked = conversationsApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const BUYER = { id: 2, name: "Dhaka Fresh Mart", email: "buyer@farmmarket.demo", role: "buyer" as const };

const CONV = {
  id: 7,
  farmer_id: 1,
  buyer_id: 2,
  other: { id: 1, name: "Rahim Uddin", role: "farmer" as const, district: "Gazipur" },
  listing_id: 3,
  listing_name: "Tomato",
  offer_id: null,
  unread_count: 2,
  last_message: { body: "Yes, still available.", sender_id: 1, created_at: "2026-11-17T10:00:00" },
  created_at: "2026-11-17T09:00:00",
  updated_at: "2026-11-17T10:00:00",
};

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="location">{loc.pathname}</div>;
}

function MessagesRoutes() {
  return (
    <Routes>
      <Route path="/messages" element={<MessagesPage />} />
      <Route path="/messages/:id" element={<MessagesPage />} />
      <Route path="*" element={<LocationProbe />} />
    </Routes>
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("fm_lang", "en");
  localStorage.setItem(USER_KEY, JSON.stringify(BUYER));
  vi.clearAllMocks();
});

describe("MessagesPage conversation list", () => {
  it("renders conversations with the other party, listing context and unread count", async () => {
    mocked.list.mockResolvedValue([CONV]);
    renderWithProviders(<MessagesRoutes />, { route: "/messages" });
    await waitFor(() => expect(screen.getByText("Rahim Uddin")).toBeInTheDocument());
    expect(screen.getByText(/About Tomato/)).toBeInTheDocument();
    expect(screen.getByText("Yes, still available.")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument(); // unread badge
    // Privacy note is shown; no phone number is rendered.
    expect(screen.getByText(/phone numbers are never shared/)).toBeInTheDocument();
    expect(screen.queryByText(/0171/)).not.toBeInTheDocument();
  });

  it("renders the empty state when there are no conversations", async () => {
    mocked.list.mockResolvedValue([]);
    renderWithProviders(<MessagesRoutes />, { route: "/messages" });
    await waitFor(() => expect(screen.getByText(/No conversations yet/)).toBeInTheDocument());
  });
});

describe("MessagesPage thread view", () => {
  it("renders messages and sends a reply", async () => {
    mocked.list.mockResolvedValue([CONV]);
    mocked.getMessages.mockResolvedValue([
      { id: 1, sender_id: 1, sender_name: "Rahim Uddin", body: "Yes, still available.", created_at: "2026-11-17T10:00:00", read_at: null },
    ]);
    mocked.markRead.mockResolvedValue({ marked_read: 1 });
    mocked.sendMessage.mockResolvedValue({
      id: 2, sender_id: 2, sender_name: "Dhaka Fresh Mart", body: "Great, I will order 10 kg.",
      created_at: "2026-11-17T10:05:00", read_at: null,
    });
    renderWithProviders(<MessagesRoutes />, { route: "/messages/7" });
    await waitFor(() => expect(screen.getByText("Yes, still available.")).toBeInTheDocument());
    // Opening the thread marks the incoming message read.
    await waitFor(() => expect(mocked.markRead).toHaveBeenCalledWith(7));

    fireEvent.change(screen.getByLabelText("Type your message…"), {
      target: { value: "Great, I will order 10 kg." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() =>
      expect(mocked.sendMessage).toHaveBeenCalledWith(7, "Great, I will order 10 kg.")
    );
  });

  it("shows a not-found state for an unknown conversation", async () => {
    mocked.list.mockResolvedValue([]);
    mocked.getMessages.mockResolvedValue([]);
    renderWithProviders(<MessagesRoutes />, { route: "/messages/999" });
    await waitFor(() => expect(screen.getByText("Conversation not found")).toBeInTheDocument());
  });
});

describe("MessageButton", () => {
  it("creates-or-finds the conversation and navigates to the thread", async () => {
    mocked.create.mockResolvedValue(CONV);
    renderWithProviders(
      <Routes>
        <Route
          path="/"
          element={<MessageButton otherUserId={1} listingId={3} label="Message farmer" />}
        />
        <Route path="*" element={<LocationProbe />} />
      </Routes>,
      { route: "/" }
    );
    fireEvent.click(screen.getByRole("button", { name: "Message farmer" }));
    await waitFor(() =>
      expect(mocked.create).toHaveBeenCalledWith({ other_user_id: 1, listing_id: 3, offer_id: null })
    );
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/messages/7"));
  });
});
