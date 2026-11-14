function slug(text) {
  return text.toLowerCase().replace(/ /g, "-");
}

module.exports = { slug };
