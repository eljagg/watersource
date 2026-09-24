/** Tailwind is compiled at build time into static/css/app.css (no CDN in production; CSP-friendly). */
module.exports = {
  content: ["./templates/**/*.html", "./apps/**/*.py"],
  theme: { extend: { colors: { wra: { 900: "#0c4a6e", 800: "#075985", 100: "#e0f2fe" } } } },
  plugins: [],
};
