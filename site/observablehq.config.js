// Observable Framework configuration. https://observablehq.com/framework/config
export default {
  title: "flightdeck",
  root: "src",
  // GitHub Pages serves a project site under the repository name.
  base: "/flightdeck/",
  pages: [
    {name: "Start here", path: "/"},
    {name: "Overview", path: "/overview"},
    {name: "Four clocks", path: "/four-clocks"},
    {name: "The game", path: "/game"}
  ],
  footer: "Every number on this site is the result of a query over warehouse/curated, which ./demo.sh build writes.",
  // The default theme stops prose at 640px and lets code blocks run to 960px,
  // so every paragraph ended short of the snippet under it. Text now runs to
  // the same right edge as the SQL it introduces.
  head: `<style>
#observablehq-main p,
#observablehq-main table,
#observablehq-main figure,
#observablehq-main figcaption,
#observablehq-main h1,
#observablehq-main h2,
#observablehq-main h3,
#observablehq-main h4,
#observablehq-main h5,
#observablehq-main h6 { max-width: 960px; }
#observablehq-main blockquote,
#observablehq-main ol,
#observablehq-main ul { max-width: 920px; }
</style>`
};
