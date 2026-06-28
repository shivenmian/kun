/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // status palette used by the trajectory graph + leaderboard
        status: {
          valid: "#22c55e",
          buggy: "#ef4444",
          promoted: "#eab308",
          running: "#38bdf8",
          proposed: "#94a3b8",
          rejected: "#f97316",
          forked: "#a855f7",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
