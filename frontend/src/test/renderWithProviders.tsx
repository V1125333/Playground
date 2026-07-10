import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

export function renderWithProviders(ui: ReactElement, route = "/generate", path = "/generate") {
  window.history.pushState({}, "Test route", route);
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path={path} element={ui} />
        <Route path="/generate" element={ui} />
        <Route path="/generate/:resumeId" element={ui} />
      </Routes>
    </MemoryRouter>,
  );
}
