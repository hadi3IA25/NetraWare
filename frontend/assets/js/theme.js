const STORAGE_KEY = "netraware-theme";

export function applyTheme(theme) {
  const dark = theme === "dark";
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";

  document.querySelectorAll("[data-theme-icon]").forEach((icon) => {
    icon.textContent = dark ? "☀" : "☾";
  });
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.setAttribute("aria-label", dark ? "Gunakan mode terang" : "Gunakan mode gelap");
    button.setAttribute("title", dark ? "Mode terang" : "Mode gelap");
  });
}

export function initTheme() {
  const saved = localStorage.getItem(STORAGE_KEY);
  const preferred = window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  applyTheme(saved || preferred);

  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const next = document.documentElement.classList.contains("dark") ? "light" : "dark";
      localStorage.setItem(STORAGE_KEY, next);
      applyTheme(next);
    });
  });
}
