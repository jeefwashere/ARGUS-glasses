/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        argus: {
          paper: "#f4f1ea",
          ink: "#11110f",
          muted: "#6f6b62",
          line: "#d6d0c3",
          metal: "#b7bbb8",
          signal: "#cfdcd5"
        }
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "SFMono-Regular", "monospace"]
      }
    }
  },
  plugins: []
};
