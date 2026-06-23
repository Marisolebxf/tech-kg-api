const crypto = require('node:crypto')

if (typeof crypto.hash !== 'function') {
  crypto.hash = function hash(algorithm, data, outputEncoding) {
    return crypto.createHash(algorithm).update(data).digest(outputEncoding)
  }
}
