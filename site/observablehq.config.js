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
  footer: "Every number on this site is the result of a query over warehouse/curated, which ./demo.sh build writes."
};
