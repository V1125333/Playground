import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useResumeAutosave } from "./useResumeAutosave";

describe("useResumeAutosave", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("does nothing when not dirty or disabled", () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderHook(({ value }) => useResumeAutosave({ value, enabled: false, delayMs: 100, onSave }), {
      initialProps: { value: { text: "draft" } },
    });

    act(() => vi.advanceTimersByTime(200));
    expect(onSave).not.toHaveBeenCalled();
  });

  it("saves after debounce when dirty and sends only the latest state", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const { rerender, result } = renderHook(({ value }) => useResumeAutosave({ value, enabled: true, delayMs: 100, onSave }), {
      initialProps: { value: { text: "initial" } },
    });

    rerender({ value: { text: "first edit" } });
    rerender({ value: { text: "latest edit" } });
    expect(result.current.status).toBe("dirty");
    expect(onSave).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(100);
      await Promise.resolve();
    });
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith({ text: "latest edit" });
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.status).toBe("saved");
  });

  it("exposes saving, saved, and error states", async () => {
    let resolveSave: () => void = () => {};
    const onSave = vi.fn().mockReturnValue(new Promise<void>((resolve) => {
      resolveSave = resolve;
    }));
    const { rerender, result } = renderHook(({ value }) => useResumeAutosave({ value, enabled: true, delayMs: 100, onSave }), {
      initialProps: { value: { text: "initial" } },
    });

    rerender({ value: { text: "edit" } });
    await act(async () => {
      vi.advanceTimersByTime(100);
      await Promise.resolve();
    });
    expect(result.current.status).toBe("saving");

    await act(async () => resolveSave());
    expect(result.current.status).toBe("saved");

    onSave.mockRejectedValueOnce(new Error("Save failed."));
    rerender({ value: { text: "second edit" } });
    await act(async () => {
      vi.advanceTimersByTime(100);
      await Promise.resolve();
    });
    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe("Save failed.");
  });

  it("cancels timers on unmount", () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const { rerender, unmount } = renderHook(({ value }) => useResumeAutosave({ value, enabled: true, delayMs: 100, onSave }), {
      initialProps: { value: { text: "initial" } },
    });

    rerender({ value: { text: "edit" } });
    unmount();
    act(() => vi.advanceTimersByTime(100));
    expect(onSave).not.toHaveBeenCalled();
  });

  it("does not issue overlapping saves and handles a newer edit during an in-flight save", async () => {
    let resolveFirstSave: () => void = () => {};
    const onSave = vi.fn().mockReturnValueOnce(new Promise<void>((resolve) => {
      resolveFirstSave = resolve;
    })).mockResolvedValue(undefined);
    const { rerender } = renderHook(({ value }) => useResumeAutosave({ value, enabled: true, delayMs: 100, onSave }), {
      initialProps: { value: { text: "initial" } },
    });

    rerender({ value: { text: "first edit" } });
    await act(async () => {
      vi.advanceTimersByTime(100);
      await Promise.resolve();
    });
    expect(onSave).toHaveBeenCalledTimes(1);

    rerender({ value: { text: "newer edit" } });
    await act(async () => {
      vi.advanceTimersByTime(100);
      await Promise.resolve();
    });
    expect(onSave).toHaveBeenCalledTimes(1);

    await act(async () => resolveFirstSave());
    expect(onSave).toHaveBeenCalledTimes(2);
    expect(onSave).toHaveBeenLastCalledWith({ text: "newer edit" });
  });
});
