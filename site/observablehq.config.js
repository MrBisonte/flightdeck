// Observable Framework configuration. https://observablehq.com/framework/config
import {readFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
import {dirname, join} from "node:path";

// Read the presentation assets at build time and inline them into <head>.
//
// Inlining rather than linking is deliberate. A <link> would need a path that
// is correct under both `npm run dev`, which serves at /, and the built site,
// which serves under /flightdeck/. Inlining has no path to get wrong, and the
// switch has to run before first paint anyway to avoid a flash of the other
// view.
const here = dirname(fileURLToPath(import.meta.url));
const asset = (name) => readFileSync(join(here, "src", "components", name), "utf-8");

export default {
  title: "flightdeck",
  root: "src",
  // GitHub Pages serves a project site under the repository name.
  base: "/flightdeck/",
  pages: [
    {name: "Start here", path: "/"},
    {name: "Overview", path: "/overview"},
    {name: "Four clocks", path: "/four-clocks"},
    {name: "The game", path: "/game"},
    {name: "Governance", path: "/governance"},
    {name: "Explore", path: "/explore"}
  ],
  // The sticky header in presentation.css carries the page links instead, so
  // both views get the same navigation. The pager stays: it is the only thing
  // that kept the reading order the sidebar used to show.
  sidebar: false,
  pager: true,
  // Both views now own their palette. Engineering overrides every --theme-*
  // variable, so the base only has to stop painting a light page underneath.
  theme: "dark",
  // Framework links Source Serif 4 from fonts.googleapis.com for every theme.
  // Nothing on this site sets it, and the site should make no third-party
  // request at view time, so the default list is emptied rather than overridden
  // in CSS, which would still fetch the face. See the type block in
  // presentation.css for what carries the page instead.
  globalStylesheets: [],
  footer: "Every number on this site is the result of a query over warehouse/curated, which ./demo.sh build writes.",
  head: [
    // The default theme caps prose at 640px while code blocks run to 960px, so
    // every paragraph stopped short of the SQL under it.
    "<style>",
    "#observablehq-main p,",
    "#observablehq-main table,",
    "#observablehq-main figure,",
    "#observablehq-main figcaption,",
    "#observablehq-main h1,",
    "#observablehq-main h2,",
    "#observablehq-main h3,",
    "#observablehq-main h4,",
    "#observablehq-main h5,",
    "#observablehq-main h6 { max-width: 960px; }",
    "#observablehq-main blockquote,",
    "#observablehq-main ol,",
    "#observablehq-main ul { max-width: 920px; }",
    "</style>",
    "<style>" + asset("presentation.css") + "</style>",
    "<script>" + asset("presentation.js") + "</script>"
  ].join("\n")
};
