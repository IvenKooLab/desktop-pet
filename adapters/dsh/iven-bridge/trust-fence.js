/** Same Host/Origin fence used by loci-dsh and the DSH API gateway.
 * This prevents browser cross-site requests and DNS rebinding; it is not auth.
 */
export function isTrustedApiRequest(request, trustedHosts = []) {
  const headers = request.headers ?? {}
  const host = typeof headers.host === 'string' ? headers.host : ''
  let hostUrl
  try { hostUrl = new URL(`http://${host}`) } catch { return false }
  if (!host || hostUrl.username || hostUrl.password || hostUrl.pathname !== '/') return false
  const hostname = hostUrl.hostname
  const parts = hostname.split('.')
  const loopback = hostname === 'localhost' || hostname === '[::1]'
    || (parts.length === 4 && parts[0] === '127' && parts.every(part => /^\d{1,3}$/.test(part) && +part <= 255))
  const trusted = trustedHosts.some(entry => {
    try {
      const url = new URL(`http://${entry}`)
      // URL strips the default HTTP port; use HTTPS to distinguish an explicit :80.
      const hasPort = url.port !== '' || new URL(`https://${entry}`).port !== ''
      return hasPort ? url.host === hostUrl.host : url.hostname === hostname
    } catch { return false }
  })
  if (!loopback && !trusted) return false
  if (headers['sec-fetch-site'] === 'cross-site') return false
  if (headers.origin === undefined) return true
  try {
    const origin = new URL(headers.origin)
    return ['http:', 'https:'].includes(origin.protocol) && origin.host === hostUrl.host
  } catch { return false }
}
