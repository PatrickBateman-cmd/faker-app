import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ThemeSwitcher } from "./ThemeSwitcher";

describe("ThemeSwitcher", () => {
  it("renders theme options", () => {
    render(<ThemeSwitcher />);
    expect(screen.getByText("Mocha")).toBeInTheDocument();
    expect(screen.getByText("Latte")).toBeInTheDocument();
  });

  it("defaults to Mocha theme", () => {
    render(<ThemeSwitcher />);
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect(select.value).toBe("theme-mocha");
  });
});
