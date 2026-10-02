# Logger Utility

Simple TypeScript utility for formatted console logging with timestamps and severity levels.

## Features

- **Simple API**: Single `log()` function with message and optional level parameter
- **ISO 8601 Timestamps**: Automatic UTC timestamp formatting (`2025-10-31T14:30:00.000Z`)
- **Three Severity Levels**: `info` (default), `warn`, `error`
- **Type-Safe**: Full TypeScript support with union types
- **Console-Only**: No file persistence, optimized for development/debugging
- **Zero Dependencies**: Uses native JavaScript `Date` and console methods

## Installation

The logger is available in `src/utils/logger.ts`. Import it in your project:

```typescript
import { log, LogLevel } from './utils/logger';
```

## API Reference

### `log(message: string, level?: LogLevel): void`

Outputs a formatted log message to the console with timestamp and severity level.

**Parameters:**
- `message` (string): The message to log
- `level` (LogLevel, optional): The severity level. Defaults to `'info'`

**Output Format:**
```
[timestamp] [LEVEL] message
```

**Example:**
```typescript
log('Application started');
// [2025-10-31T14:30:00.000Z] [INFO] Application started
```

### `LogLevel` Type

Type-safe union of supported log levels:

```typescript
type LogLevel = 'info' | 'warn' | 'error';
```

**Behavior:**
- `info`: Routes to `console.log()` (standard output)
- `warn`: Routes to `console.warn()` (typically yellow in browsers/terminals)
- `error`: Routes to `console.error()` (typically red in browsers/terminals)

## Usage Examples

### Basic Logging

```typescript
import { log } from './utils/logger';

// Default level (info)
log('Application started');
// [2025-10-31T14:30:00.000Z] [INFO] Application started

// Explicit info level
log('Configuration loaded', 'info');
// [2025-10-31T14:30:01.000Z] [INFO] Configuration loaded
```

### Warning Messages

```typescript
log('Deprecated API usage detected', 'warn');
// [2025-10-31T14:30:02.000Z] [WARN] Deprecated API usage detected

log('Large dataset may impact performance', 'warn');
// [2025-10-31T14:30:03.000Z] [WARN] Large dataset may impact performance
```

### Error Messages

```typescript
log('Database connection failed', 'error');
// [2025-10-31T14:30:04.000Z] [ERROR] Database connection failed

log('Invalid API response format', 'error');
// [2025-10-31T14:30:05.000Z] [ERROR] Invalid API response format
```

### Integration in Application Code

```typescript
import { log } from './utils/logger';

function processData(data: string[]): void {
  log(`Processing ${data.length} items`);

  try {
    // Processing logic...
    data.forEach(item => {
      // ... process item
    });
    log('Data processed successfully');
  } catch (error) {
    log(`Processing failed: ${error.message}`, 'error');
  }
}
```

### Conditional Logging

```typescript
import { log, LogLevel } from './utils/logger';

function debugLog(message: string, condition: boolean): void {
  if (condition) {
    log(message, 'warn');
  }
}

// Usage
const isDevelopment = process.env.NODE_ENV === 'development';
debugLog('Debug mode enabled', isDevelopment);
```

### Error Handling Pattern

```typescript
import { log } from './utils/logger';

async function fetchData(url: string): Promise<any> {
  log(`Fetching data from ${url}`);

  try {
    const response = await fetch(url);

    if (!response.ok) {
      log(`HTTP error: ${response.status} ${response.statusText}`, 'error');
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    log('Data fetched successfully');
    return data;

  } catch (error) {
    log(`Fetch failed: ${error.message}`, 'error');
    throw error;
  }
}
```

## Output Format Details

### Timestamp Format

- **Standard**: ISO 8601 UTC format
- **Example**: `2025-10-31T14:30:00.000Z`
- **Components**: `YYYY-MM-DDTHH:mm:ss.sssZ`
- **Timezone**: Always UTC (indicated by `Z`)

### Log Level Format

- **Uppercase**: All levels are uppercase in output (`INFO`, `WARN`, `ERROR`)
- **Fixed Width**: Aligned for readability in console

### Complete Format

```
[2025-10-31T14:30:00.000Z] [INFO] Application started
[2025-10-31T14:30:01.000Z] [WARN] Deprecated API usage
[2025-10-31T14:30:02.000Z] [ERROR] Database connection failed
```

## Console Method Routing

The logger routes messages to appropriate console methods based on severity:

| Level   | Console Method  | Typical Display       |
|---------|----------------|----------------------|
| `info`  | `console.log`  | Default (white/black)|
| `warn`  | `console.warn` | Yellow/orange        |
| `error` | `console.error`| Red                  |

**Benefits:**
- Native browser/Node.js styling
- Proper log level filtering in browser dev tools
- Better debugging experience
- Stacktrace included for errors (browser/Node.js default behavior)

## Type Safety

TypeScript prevents invalid log levels at compile time:

```typescript
log('Valid message', 'info');   // ✅ Valid
log('Valid message', 'warn');   // ✅ Valid
log('Valid message', 'error');  // ✅ Valid
log('Invalid message', 'debug'); // ❌ Type error: 'debug' not assignable to LogLevel
```

IDE autocomplete suggests valid options:

```typescript
log('Message', /* autocomplete shows: 'info' | 'warn' | 'error' */);
```

## Testing

The logger includes comprehensive unit tests covering:

1. Default behavior (info level)
2. Explicit info level
3. Warn level
4. Error level
5. Timestamp format validation (ISO 8601)
6. Message formatting

**Run tests:**
```bash
npm test src/utils/__tests__/logger.spec.ts
```

**Coverage:**
- 100% function coverage
- 100% line coverage
- 100% branch coverage

## Technical Decisions

### Why ISO 8601 Timestamps?

- **Standard format**: Universal, sortable
- **Timezone-aware**: UTC prevents confusion
- **No dependencies**: Native `Date.toISOString()`
- **Parseable**: Can be parsed back to Date object

### Why Union Type for LogLevel?

- **Type safety**: Compile-time validation
- **IDE support**: Autocomplete and inline documentation
- **Prevents typos**: Invalid levels caught early
- **Simple and clear**: Easy to understand and extend

### Why Separate Console Methods?

- **Native styling**: Browsers/terminals color-code automatically
- **Better filtering**: Dev tools can filter by console method
- **Improved debugging**: Errors include stacktraces
- **Standard practice**: Follows console API conventions

### Why No Advanced Features?

- **KISS principle**: Keep implementation simple
- **Task requirements**: Specified "simple console logger"
- **Extensibility**: Advanced features can be added later
- **Zero dependencies**: No external libraries required

## Non-Goals

The logger intentionally does **not** include:

- ❌ File logging (console only)
- ❌ Log rotation
- ❌ Remote logging (e.g., Sentry, LogRocket)
- ❌ Custom formatters
- ❌ Additional log levels (e.g., debug, trace, fatal)
- ❌ Performance optimization (buffering, async)
- ❌ Browser-specific compatibility

If your project requires these features, consider using a dedicated logging library like Winston, Pino, or Bunyan.

## Performance Considerations

**Minimal Overhead:**
- Single `Date.toISOString()` call per log
- String template interpolation
- No external dependencies
- No async operations

**Synchronous Behavior:**
- Logs are output immediately
- No buffering or queuing
- Console methods are synchronous in Node.js

**Production Use:**
- Consider disabling verbose logging in production
- Use environment variables to control log levels
- Implement conditional logging wrapper if needed

## Migration Guide

### From console.log()

**Before:**
```typescript
console.log('Application started');
console.log('Warning:', warning);
console.error('Error:', error);
```

**After:**
```typescript
import { log } from './utils/logger';

log('Application started');
log(`Warning: ${warning}`, 'warn');
log(`Error: ${error}`, 'error');
```

### From Custom Logger

**Before:**
```typescript
logger.info('Message');
logger.warn('Warning');
logger.error('Error');
```

**After:**
```typescript
import { log } from './utils/logger';

log('Message');
log('Warning', 'warn');
log('Error', 'error');
```

## Best Practices

### 1. Use Appropriate Levels

```typescript
// ✅ Good
log('User logged in');                      // info
log('API rate limit approaching', 'warn');  // warn
log('Database connection failed', 'error'); // error

// ❌ Avoid
log('Critical error occurred');             // Should be 'error' level
log('Invalid configuration', 'info');       // Should be 'error' or 'warn'
```

### 2. Include Context in Messages

```typescript
// ✅ Good
log(`User ${userId} completed checkout`);
log(`Failed to load resource: ${resourceId}`, 'error');

// ❌ Avoid
log('User completed checkout');             // Missing user ID
log('Failed to load resource', 'error');   // Missing resource details
```

### 3. Avoid Logging Sensitive Data

```typescript
// ✅ Good
log(`Authentication attempt for user ${userId}`);

// ❌ Avoid
log(`Authentication attempt with password ${password}`); // Exposes password
log(`API key: ${apiKey}`);                              // Exposes credentials
```

### 4. Log Important State Transitions

```typescript
function processOrder(orderId: string): void {
  log(`Starting order processing: ${orderId}`);

  // ... processing logic

  log(`Order ${orderId} completed successfully`);
}
```

## Future Extensibility

The logger is designed for easy extension:

### Adding Log Levels

```typescript
// Extend LogLevel type
export type LogLevel = 'info' | 'warn' | 'error' | 'debug' | 'trace';

// Update switch statement in log() function
switch (level) {
  case 'error':
    console.error(formattedMessage);
    break;
  case 'warn':
    console.warn(formattedMessage);
    break;
  case 'debug':
    console.debug(formattedMessage);
    break;
  case 'trace':
    console.trace(formattedMessage);
    break;
  case 'info':
  default:
    console.log(formattedMessage);
    break;
}
```

### Adding Configuration Options

```typescript
// Use LogOptions interface (currently reserved)
export interface LogOptions {
  level?: LogLevel;
  includeTimestamp?: boolean;
  timestampFormat?: 'iso' | 'local';
}

export function log(message: string, options: LogOptions = {}): void {
  // Implementation with options...
}
```

## License

Part of the Navigator project. See project LICENSE for details.

## Version

**Current Version**: 1.0.0
**Created**: 2025-10-31
**Last Updated**: 2025-10-31

## Related Documentation

- Implementation Plan: `.agent/tasks/TASK-22-simple-console-logger.md`
- Test Suite: `src/utils/__tests__/logger.spec.ts`
- Source Code: `src/utils/logger.ts`
