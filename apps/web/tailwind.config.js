/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        paypal: {
          blue: "#003087",
          dark: "#001C64",
          light: "#0079C1",
          gold: "#FFC439",
          slate: "#001435"
        }
      }
    },
  },
  plugins: [],
}
