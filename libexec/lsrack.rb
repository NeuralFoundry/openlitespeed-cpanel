require 'socket'
require 'stringio'
require 'tempfile'
require 'etc'

MAX_LINE = 65536
MAX_HEADERS = 200
MEMORY_BODY = 1 << 20
MAX_BODY = 2047 << 20
STATE = { seen: Time.now.to_f, active: 0 }
LOCK = Mutex.new
REASONS = {
  200 => 'OK', 201 => 'Created', 202 => 'Accepted', 204 => 'No Content', 206 => 'Partial Content',
  301 => 'Moved Permanently', 302 => 'Found', 303 => 'See Other', 304 => 'Not Modified',
  307 => 'Temporary Redirect', 308 => 'Permanent Redirect', 400 => 'Bad Request', 401 => 'Unauthorized',
  403 => 'Forbidden', 404 => 'Not Found', 405 => 'Method Not Allowed', 409 => 'Conflict', 410 => 'Gone',
  413 => 'Payload Too Large', 422 => 'Unprocessable Entity', 429 => 'Too Many Requests',
  500 => 'Internal Server Error', 502 => 'Bad Gateway', 503 => 'Service Unavailable'
}.freeze

class BadRequest < StandardError; end

def redirect_output
  log = ENV['LS_STDERR_LOG'].to_s
  return if log.empty?
  log = File.expand_path(log)
  dir = File.dirname(log)
  Dir.mkdir(dir, 0o700) unless File.directory?(dir)
  f = File.open(log, 'a')
  f.sync = true
  $stderr.reopen(f)
  $stdout.reopen(f)
rescue SystemCallError
  nil
end

def listener
  begin
    io = IO.for_fd(0, autoclose: false)
    if io.stat.socket?
      sock = Socket.for_fd(0)
      sock.autoclose = false
      return UNIXServer.for_fd(0) if sock.getsockopt(Socket::SOL_SOCKET, Socket::SO_ACCEPTCONN).int != 0
    end
  rescue SystemCallError, IOError
    nil
  end
  path = ENV['LSNODE_SOCKET'].to_s
  abort('no listening socket') if path.empty?
  File.unlink(path) if File.exist?(path)
  UNIXServer.new(path)
end

def load_app(root, startup)
  gemfile = File.join(root, 'Gemfile')
  if File.file?(gemfile)
    ENV['BUNDLE_GEMFILE'] ||= gemfile
    require 'bundler/setup'
  end
  require 'rack'
  path = File.expand_path(startup, root)
  app = Rack::Builder.parse_file(path)
  app = app[0] if app.is_a?(Array)
  app
end

def reason(status)
  if defined?(Rack::Utils::HTTP_STATUS_CODES) && Rack::Utils::HTTP_STATUS_CODES[status]
    Rack::Utils::HTTP_STATUS_CODES[status]
  else
    REASONS[status] || 'Unknown'
  end
end

def read_line(io)
  line = io.gets("\n", MAX_LINE + 1)
  return nil if line.nil?
  raise BadRequest, 'line too long' if line.bytesize > MAX_LINE
  line.chomp("\n").chomp("\r")
end

def read_head(io)
  line = read_line(io)
  line = read_line(io) while line == ''
  return nil if line.nil?
  method, target, version = line.split(' ', 3)
  raise BadRequest, 'bad request line' unless method && target && version && version.start_with?('HTTP/1.')
  headers = []
  loop do
    h = read_line(io)
    raise BadRequest, 'truncated headers' if h.nil?
    break if h.empty?
    raise BadRequest, 'too many headers' if headers.size >= MAX_HEADERS
    if h.start_with?(' ', "\t") && !headers.empty?
      headers[-1][1] = headers[-1][1] + ' ' + h.strip
      next
    end
    name, value = h.split(':', 2)
    raise BadRequest, 'bad header' if value.nil? || name !~ /\A[!#$%&'*+.^_`|~0-9A-Za-z-]+\z/
    headers << [name, value.strip]
  end
  [method, target, version, headers]
end

def spool(size)
  if size > MEMORY_BODY
    t = Tempfile.new('lsrack')
    t.unlink
    t.binmode
    t
  else
    StringIO.new(String.new(encoding: Encoding::BINARY))
  end
end

def read_body(io, headers)
  te = headers.select { |k, _| k.casecmp('transfer-encoding').zero? }.map { |_, v| v.downcase }
  if te.any? { |v| v.include?('chunked') }
    body = spool(MEMORY_BODY + 1)
    total = 0
    loop do
      size_line = read_line(io)
      raise BadRequest, 'truncated body' if size_line.nil?
      size = Integer((size_line.split(';', 2)[0] || '').strip, 16)
      break if size.zero?
      total += size
      raise BadRequest, 'body too large' if size.negative? || total > MAX_BODY
      left = size
      while left > 0
        chunk = io.read([left, 65536].min)
        raise BadRequest, 'truncated body' if chunk.nil? || chunk.empty?
        body.write(chunk)
        left -= chunk.bytesize
      end
      io.read(2)
    end
    loop do
      t = read_line(io)
      break if t.nil? || t.empty?
    end
    body.rewind
    return [body, body.size]
  end
  cl = headers.reverse.find { |k, _| k.casecmp('content-length').zero? }
  len = cl ? Integer(cl[1], 10) : 0
  raise BadRequest, 'bad content length' if len.negative? || len > MAX_BODY
  body = spool(len)
  left = len
  while left > 0
    chunk = io.read([left, 65536].min)
    raise BadRequest, 'truncated body' if chunk.nil? || chunk.empty?
    body.write(chunk)
    left -= chunk.bytesize
  end
  body.rewind
  [body, len]
rescue ArgumentError
  raise BadRequest, 'bad body framing'
end

def build_env(method, target, version, headers, body, len, prefix)
  path, query = target.split('?', 2)
  path = '/' if path.nil? || path.empty?
  env = {
    'REQUEST_METHOD' => method, 'SCRIPT_NAME' => '', 'PATH_INFO' => path, 'QUERY_STRING' => query.to_s,
    'REQUEST_URI' => target, 'REQUEST_PATH' => path, 'SERVER_NAME' => 'localhost', 'SERVER_PORT' => '80',
    'SERVER_PROTOCOL' => version, 'HTTP_VERSION' => version, 'SERVER_SOFTWARE' => 'olscp',
    'GATEWAY_INTERFACE' => 'CGI/1.1', 'REMOTE_ADDR' => '127.0.0.1',
    'rack.version' => [1, 3], 'rack.url_scheme' => 'http', 'rack.input' => body, 'rack.errors' => $stderr,
    'rack.multithread' => true, 'rack.multiprocess' => false, 'rack.run_once' => false,
    'rack.hijack?' => false
  }
  headers.each do |name, value|
    key = name.upcase.tr('-', '_')
    next if name.include?('_')
    if key == 'CONTENT_TYPE' || key == 'CONTENT_LENGTH'
      env[key] = value
    else
      k = 'HTTP_' + key
      env[k] = env.key?(k) ? (k == 'HTTP_COOKIE' ? "#{env[k]}; #{value}" : "#{env[k]}, #{value}") : value
    end
  end
  env['CONTENT_LENGTH'] = len.to_s if len > 0 || env.key?('CONTENT_LENGTH')
  env.delete('HTTP_TRANSFER_ENCODING')
  fwd = env['HTTP_X_FORWARDED_FOR'].to_s
  unless fwd.empty?
    last = fwd.split(',').last.to_s.strip
    env['REMOTE_ADDR'] = last unless last.empty?
  end
  if env['HTTP_X_FORWARDED_PROTO'].to_s.downcase == 'https'
    env['rack.url_scheme'] = 'https'
    env['HTTPS'] = 'on'
    env['SERVER_PORT'] = '443'
  end
  host = env['HTTP_HOST'].to_s
  unless host.empty?
    if host.rindex(':') && host.rindex(':') > (host.rindex(']') || -1)
      name, port = host[0...host.rindex(':')], host[(host.rindex(':') + 1)..-1]
      env['SERVER_NAME'] = name.empty? ? host : name
      env['SERVER_PORT'] = port if port =~ /\A\d+\z/
    else
      env['SERVER_NAME'] = host
    end
  end
  if !prefix.empty? && (path == prefix || path.start_with?(prefix + '/'))
    env['SCRIPT_NAME'] = prefix
    env['PATH_INFO'] = path[prefix.length..-1]
  end
  env
end

def header_pairs(headers)
  out = []
  headers.each do |name, value|
    name = name.to_s
    next if name !~ /\A[!#$%&'*+.^_`|~0-9A-Za-z-]+\z/ || name.casecmp('status').zero?
    values = value.is_a?(Array) ? value : value.to_s.split("\n")
    values.each do |v|
      v = v.to_s
      next if v =~ /[\r\n\0]/
      out << [name, v]
    end
  end
  out
end

def write_response(io, method, version, keep, status, headers, body)
  status = status.to_i
  pairs = header_pairs(headers)
  names = pairs.map { |k, _| k.downcase }
  no_body = method == 'HEAD' || status < 200 || status == 204 || status == 304
  chunked = false
  unless no_body || names.include?('content-length') || names.include?('transfer-encoding')
    if version == 'HTTP/1.1'
      chunked = true
      pairs << ['Transfer-Encoding', 'chunked']
    else
      keep = false
    end
  end
  pairs.reject! { |k, _| k.casecmp('connection').zero? }
  pairs << ['Connection', keep ? 'keep-alive' : 'close']
  head = String.new("HTTP/1.1 #{status} #{reason(status)}\r\n", encoding: Encoding::BINARY)
  pairs.each { |k, v| head << k.b << ': '.b << v.b << "\r\n".b }
  io.write(head << "\r\n".b)
  unless no_body
    body.each do |chunk|
      chunk = chunk.to_s.b
      next if chunk.empty?
      io.write(chunked ? "#{chunk.bytesize.to_s(16)}\r\n#{chunk}\r\n" : chunk)
    end
    io.write("0\r\n\r\n") if chunked
  end
  keep
ensure
  body.close if body.respond_to?(:close)
end

def keep_alive?(version, headers)
  conn = headers.select { |k, _| k.casecmp('connection').zero? }.map { |_, v| v.downcase }.join(',')
  return conn.include?('keep-alive') if version == 'HTTP/1.0'
  !conn.include?('close')
end

def serve(client, app, prefix)
  loop do
    head = read_head(client)
    break if head.nil?
    method, target, version, headers = head
    body, len = read_body(client, headers)
    LOCK.synchronize { STATE[:active] += 1 }
    begin
      env = build_env(method, target, version, headers, body, len, prefix)
      keep = keep_alive?(version, headers)
      begin
        status, rheaders, rbody = app.call(env)
      rescue StandardError, ScriptError => e
        warn "#{e.class}: #{e.message}\n#{(e.backtrace || []).first(20).join("\n")}"
        status, rheaders, rbody = 500, { 'Content-Type' => 'text/plain' }, ['Internal Server Error']
      end
      keep = write_response(client, method, version, keep, status, rheaders, rbody)
    ensure
      body.close if body.respond_to?(:close)
      LOCK.synchronize do
        STATE[:active] -= 1
        STATE[:seen] = Time.now.to_f
      end
    end
    break unless keep
  end
rescue BadRequest
  begin
    client.write("HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
  rescue SystemCallError, IOError
    nil
  end
rescue SystemCallError, IOError
  nil
rescue StandardError => e
  warn "#{e.class}: #{e.message}"
ensure
  client.close unless client.closed?
end

def idle_exit(limit)
  Thread.new do
    loop do
      sleep([30, limit].min)
      idle = LOCK.synchronize { STATE[:active].zero? && Time.now.to_f - STATE[:seen] > limit }
      exit!(0) if idle
    end
  end
end

def main
  redirect_output
  ENV['HOME'] = Etc.getpwuid(Process.uid).dir if ENV['HOME'].to_s.empty?
  root = File.expand_path(ENV['LSNODE_ROOT'].to_s.empty? ? Dir.pwd : ENV['LSNODE_ROOT'])
  startup = ENV['LSNODE_STARTUP_FILE'].to_s.empty? ? 'config.ru' : ENV['LSNODE_STARTUP_FILE']
  mode = ENV['PASSENGER_APP_ENV'].to_s
  unless mode.empty?
    ENV['RACK_ENV'] ||= mode
    ENV['RAILS_ENV'] ||= mode
  end
  Dir.chdir(root)
  server = listener
  app = load_app(root, startup)
  prefix = (ENV['OLSCP_APP_URI'] || '/').sub(%r{/+\z}, '')
  trap('TERM') { exit!(0) }
  limit = ENV['LSAPI_PGRP_MAX_IDLE'].to_i
  idle_exit(limit) if limit > 0
  loop do
    client = server.accept
    Thread.new(client) { |c| serve(c, app, prefix) }
  end
end

main if $PROGRAM_NAME == __FILE__
