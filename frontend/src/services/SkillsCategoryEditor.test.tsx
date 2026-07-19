import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { SkillsCategoryEditor } from "../App";
import { approvedSkillCategoryDefinition, normalizeSkillName, splitSkillValues } from "./skillsData";

type TestSkillCategory = {
  categoryId: string;
  categoryName: string;
  order: number;
  items: string[];
  pendingSkill: string;
  collapsed: boolean;
  migrationReviewRequired: boolean;
};

function EditorHarness() {
  const [categories, setCategories] = useState<TestSkillCategory[]>([
    {
      categoryId: "programming-languages",
      categoryName: "Programming Languages",
      order: 0,
      items: ["C#", "JavaScript"],
      pendingSkill: "",
      collapsed: false,
      migrationReviewRequired: false,
    },
    {
      categoryId: "backend-net",
      categoryName: "Backend / .NET",
      order: 1,
      items: ["ASP.NET Core"],
      pendingSkill: "",
      collapsed: true,
      migrationReviewRequired: false,
    },
  ]);

  return (
    <SkillsCategoryEditor
      categories={categories}
      duplicateWarnings={[]}
      migratedSkillLabelCount={0}
      disabled={false}
      onFixMigratedSkillLabels={() => undefined}
      onAddCategory={(categoryId) => {
        const definition = approvedSkillCategoryDefinition(categoryId);
        if (!definition || categories.some((category) => category.categoryId === definition.categoryId)) return;
        setCategories((current) => [
          ...current,
          {
            categoryId: definition.categoryId,
            categoryName: definition.categoryName,
            order: current.length,
            items: [],
            pendingSkill: "",
            collapsed: false,
            migrationReviewRequired: false,
          },
        ]);
      }}
      onMoveCategory={(categoryId, direction) => {
        setCategories((current) => {
          const index = current.findIndex((item) => item.categoryId === categoryId);
          const target = index + direction;
          if (index < 0 || target < 0 || target >= current.length) return current;
          const next = [...current];
          const [item] = next.splice(index, 1);
          next.splice(target, 0, item);
          return next.map((category, order) => ({ ...category, order }));
        });
      }}
      onRemoveCategory={(categoryId) => {
        setCategories((current) => current.filter((category) => category.categoryId !== categoryId));
      }}
      onUpdateCategory={(categoryId, field, value) => {
        setCategories((current) => current.map((category) => category.categoryId === categoryId ? { ...category, [field]: value } : category));
      }}
      onAddSkill={(categoryId) => {
        setCategories((current) => current.map((category) => {
          if (category.categoryId !== categoryId) return category;
          const existing = new Set(category.items.map((item) => item.toLowerCase()));
          const additions = splitSkillValues(category.pendingSkill).filter((item) => !existing.has(item.toLowerCase()));
          return { ...category, items: [...category.items, ...additions], pendingSkill: "" };
        }));
      }}
      onUpdateSkill={(categoryId, previousSkill, nextSkill) => {
        setCategories((current) => current.map((category) => {
          if (category.categoryId !== categoryId) return category;
          return { ...category, items: category.items.map((item) => item === previousSkill ? normalizeSkillName(nextSkill) : item) };
        }));
      }}
      onRemoveSkill={(categoryId, skill) => {
        setCategories((current) => current.map((category) => category.categoryId === categoryId
          ? { ...category, items: category.items.filter((item) => item !== skill) }
          : category));
      }}
    />
  );
}

function MigratedEditorHarness() {
  const [categories, setCategories] = useState<TestSkillCategory[]>([
    {
      categoryId: "technical-skills",
      categoryName: "Technical Skills",
      order: 0,
      items: [
        "Programming Languages: C#",
        "JavaScript",
        "Backend /.NET: ASP.NET Core",
        "Cloud: Microsoft Azure (App Service",
        "Azure SQL)",
      ],
      pendingSkill: "",
      collapsed: false,
      migrationReviewRequired: true,
    },
  ]);

  const toProfileCategory = (category: TestSkillCategory) => ({
    category: category.categoryName,
    categoryId: category.categoryId,
    categoryName: category.categoryName,
    order: category.order,
    items: category.items,
    migrationReviewRequired: category.migrationReviewRequired,
  });

  return (
    <SkillsCategoryEditor
      categories={categories}
      duplicateWarnings={[]}
      migratedSkillLabelCount={categories.reduce((count, category) => count + category.items.filter((item) => item.includes(":")).length, 0)}
      disabled={false}
      onFixMigratedSkillLabels={() => {
        import("./skillsData").then(({ repairCategoryLabelSkills }) => {
          setCategories(repairCategoryLabelSkills(categories.map(toProfileCategory)).map((category) => ({
            categoryId: category.categoryId ?? category.category,
            categoryName: category.categoryName ?? category.category,
            order: category.order ?? 0,
            items: category.items,
            pendingSkill: "",
            collapsed: (category.order ?? 0) !== 0,
            migrationReviewRequired: false,
          })));
        });
      }}
      onAddCategory={() => undefined}
      onMoveCategory={() => undefined}
      onRemoveCategory={() => undefined}
      onUpdateCategory={(categoryId, field, value) => {
        setCategories((current) => current.map((category) => category.categoryId === categoryId ? { ...category, [field]: value } : category));
      }}
      onAddSkill={() => undefined}
      onUpdateSkill={() => undefined}
      onRemoveSkill={() => undefined}
    />
  );
}

describe("SkillsCategoryEditor", () => {
  it("renders as an accordion with one category expanded and another collapsed", () => {
    render(<EditorHarness />);

    expect(screen.getByText("Programming Languages")).toBeInTheDocument();
    expect(screen.getByText("C#")).toBeInTheDocument();
    expect(screen.getByText("Backend / .NET")).toBeInTheDocument();
    expect(screen.queryByText("ASP.NET Core")).not.toBeInTheDocument();
  });

  it("expands and collapses a category", async () => {
    const user = userEvent.setup();
    render(<EditorHarness />);

    await user.click(screen.getByLabelText("Expand Backend / .NET"));
    expect(screen.getByText("ASP.NET Core")).toBeInTheDocument();
    await user.click(screen.getByLabelText("Collapse Backend / .NET"));
    expect(screen.queryByText("ASP.NET Core")).not.toBeInTheDocument();
  });

  it("adds a category from a searchable approved dropdown, reorders it, and deletes it", async () => {
    const user = userEvent.setup();
    render(<EditorHarness />);

    await user.click(screen.getByRole("button", { name: /add category/i }));
    expect(screen.queryByLabelText(/new category name/i)).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /search or select a skill category/i })).toBeInTheDocument();
    expect(screen.getByText("Technical")).toBeInTheDocument();
    expect(screen.getByText("Professional")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create category/i })).toBeDisabled();

    await user.type(screen.getByRole("combobox", { name: /search or select a skill category/i }), "cloud");
    expect(screen.getByRole("option", { name: /Cloud Platforms & Services/i })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Programming Languages/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: /Cloud Platforms & Services/i }));
    expect(screen.getAllByText("Public cloud platforms and managed cloud services.").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: /create category/i }));

    expect(screen.getByText("Cloud Platforms & Services")).toBeInTheDocument();
    expect(screen.getByText("No skills added yet.")).toBeInTheDocument();

    await user.click(screen.getAllByLabelText("Move skill category up").at(-1)!);
    expect(screen.getAllByText(/Cloud Platforms & Services|Backend \/ \.NET|Programming Languages/)[1]).toHaveTextContent("Cloud Platforms & Services");

    await user.click(screen.getAllByLabelText("Delete skill category").at(1)!);
    expect(screen.queryByText("Cloud Platforms & Services")).not.toBeInTheDocument();
  });

  it("does not show existing approved categories, supports keyboard selection, and cancel leaves skills unchanged", async () => {
    const user = userEvent.setup();
    render(<EditorHarness />);

    await user.click(screen.getByRole("button", { name: /add category/i }));
    expect(screen.queryByRole("option", { name: /Programming Languages/i })).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("combobox", { name: /search or select a skill category/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Cloud Platforms & Services")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /add category/i }));
    await user.type(screen.getByRole("combobox", { name: /search or select a skill category/i }), "cloud");
    await user.keyboard("{Enter}");
    await user.click(screen.getByRole("button", { name: /create category/i }));
    expect(screen.getByText("Cloud Platforms & Services")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /add category/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.getAllByText("Cloud Platforms & Services")).toHaveLength(1);
  });

  it("adds a skill with Enter, edits it inline, and deletes a skill row", async () => {
    const user = userEvent.setup();
    render(<EditorHarness />);

    await user.click(screen.getByRole("button", { name: /add skill/i }));
    await user.type(screen.getByLabelText("Add skill to Programming Languages"), "Python{Enter}");
    expect(screen.getByText("Python")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Edit Python"));
    const editInput = screen.getAllByLabelText("Edit Python").find((element) => element.tagName === "INPUT") as HTMLInputElement;
    await user.clear(editInput);
    await user.type(editInput, "Python 3{Enter}");
    expect(screen.getByText("Python 3")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Delete JavaScript"));
    expect(screen.queryByText("JavaScript")).not.toBeInTheDocument();

    const category = screen.getByText("Programming Languages").closest("div")?.parentElement?.parentElement;
    expect(category ? within(category).getByText("2") : null).toBeInTheDocument();
  });

  it("shows migration banner and fixes label-prefixed skills automatically", async () => {
    const user = userEvent.setup();
    render(<MigratedEditorHarness />);

    expect(screen.getByText(/migrated skills that still contain category labels/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /fix automatically/i }));

    expect(await screen.findByText("Programming Languages")).toBeInTheDocument();
    expect(screen.getByText("C#")).toBeInTheDocument();
    expect(screen.getByText("Backend Development")).toBeInTheDocument();
    expect(screen.getByText("Cloud Platforms & Services")).toBeInTheDocument();
    await user.click(screen.getByLabelText("Expand Cloud Platforms & Services"));
    expect(screen.getByText("Microsoft Azure (App Service, Azure SQL)")).toBeInTheDocument();
    expect(screen.queryByText("Technical Skills")).not.toBeInTheDocument();
  });
});
