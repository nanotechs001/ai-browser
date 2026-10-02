// Where the reader of a site the user added runs: the page they picked the part to watch on, and the pages under its
// address, not the whole site (its other pages don't have that part).
export function watchPattern(address) {
  const url = new URL(address);
  const path = url.pathname.replaceAll("*", "");
  return `${url.origin}${path === "/" ? "/" : path}*`;
}
