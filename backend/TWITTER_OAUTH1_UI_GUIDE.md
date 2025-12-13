# Twitter OAuth 1.0a UI Integration Guide

## Overview

Twitter requires **OAuth 1.0a** tokens for media uploads, even though the main authentication uses **OAuth 2.0**. This means users need to complete two separate OAuth flows:
1. **OAuth 2.0** - For posting tweets (text and basic operations)
2. **OAuth 1.0a** - For uploading images/media (required for media uploads)

Both OAuth flows are stored in the **same integration** - they are not separate integrations.

## API Endpoints

### 1. Check OAuth 1.0 Status
**GET** `/api/v1/integrations/{integration_id}`

The response includes `oauth1_configured` field:
```json
{
  "id": "...",
  "platform": "twitter",
  "oauth1_configured": false,  // or true if configured
  ...
}
```

### 2. Get OAuth 1.0 Init URL
**GET** `/api/v1/integrations/{integration_id}/oauth1/init-url`

Returns:
```json
{
  "oauth1_configured": false,
  "message": "OAuth 1.0a is required for media uploads. Click to complete authorization.",
  "init_url": "http://backend/api/v1/integrations/oauth/twitter/oauth1/init",
  "required_for": "media_uploads"
}
```

If already configured:
```json
{
  "oauth1_configured": true,
  "message": "OAuth 1.0a is already configured for this integration",
  "init_url": null
}
```

### 3. OAuth 1.0 Init Endpoint
**GET** `/api/v1/integrations/oauth/twitter/oauth1/init`

This endpoint:
- Requires authentication (user must be logged in)
- Requires existing Twitter OAuth 2.0 integration
- Redirects to Twitter authorization page
- After authorization, redirects to callback

### 4. OAuth 1.0 Callback
**GET** `/api/v1/integrations/oauth/twitter/oauth1/callback`

Handled automatically by Twitter redirect. Redirects to frontend with status:
- Success: `{frontend_url}/dashboard/platform-connect?success=true&platform=twitter&oauth1=complete`
- Error: `{frontend_url}/dashboard/platform-connect?success=false&error=...`

## UI Implementation Flow

### Step 1: Display Integration Status

When showing a Twitter integration in the UI:

```typescript
// Fetch integration details
const integration = await fetch(`/api/v1/integrations/${integrationId}`);

if (integration.platform === 'twitter') {
  // Check OAuth 1.0 status
  if (!integration.oauth1_configured) {
    // Show warning/button to complete OAuth 1.0
    showOAuth1Warning(integration);
  }
}
```

### Step 2: Show OAuth 1.0 Warning/Button

Display a notice or button when OAuth 1.0 is not configured:

```tsx
{integration.platform === 'twitter' && !integration.oauth1_configured && (
  <div className="oauth1-warning">
    <Alert type="warning">
      <p>Media uploads require additional authorization.</p>
      <p>Complete OAuth 1.0a to enable image uploads for Twitter posts.</p>
      <Button onClick={handleOAuth1Init}>
        Complete Media Upload Authorization
      </Button>
    </Alert>
  </div>
)}
```

### Step 3: Handle OAuth 1.0 Init

When user clicks the button:

```typescript
async function handleOAuth1Init() {
  // Get the init URL from the API
  const response = await fetch(
    `/api/v1/integrations/${integrationId}/oauth1/init-url`
  );
  const data = await response.json();
  
  if (data.init_url) {
    // Redirect to OAuth 1.0 init endpoint
    window.location.href = data.init_url;
  }
}
```

### Step 4: Handle Callback

After Twitter redirects back, check the URL parameters:

```typescript
// In your platform-connect page or callback handler
const urlParams = new URLSearchParams(window.location.search);
const success = urlParams.get('success') === 'true';
const oauth1 = urlParams.get('oauth1') === 'complete';

if (success && oauth1) {
  // Show success message
  showNotification('Twitter media upload authorization completed!');
  
  // Refresh integration list to update oauth1_configured status
  refreshIntegrations();
}
```

## Complete UI Example

```tsx
function TwitterIntegrationCard({ integration }) {
  const [oauth1Status, setOauth1Status] = useState(null);
  
  useEffect(() => {
    if (integration.platform === 'twitter') {
      checkOAuth1Status();
    }
  }, [integration.id]);
  
  async function checkOAuth1Status() {
    const response = await fetch(
      `/api/v1/integrations/${integration.id}/oauth1/init-url`
    );
    const data = await response.json();
    setOauth1Status(data);
  }
  
  async function handleOAuth1Init() {
    if (oauth1Status?.init_url) {
      window.location.href = oauth1Status.init_url;
    }
  }
  
  return (
    <Card>
      <CardHeader>
        <h3>Twitter: {integration.platform_username}</h3>
      </CardHeader>
      <CardBody>
        {integration.platform === 'twitter' && 
         !integration.oauth1_configured && (
          <Alert type="warning">
            <AlertTitle>Media Upload Authorization Required</AlertTitle>
            <AlertDescription>
              To upload images with your Twitter posts, you need to complete 
              an additional authorization step.
            </AlertDescription>
            <Button onClick={handleOAuth1Init} className="mt-4">
              Authorize Media Uploads
            </Button>
          </Alert>
        )}
        
        {integration.oauth1_configured && (
          <Badge variant="success">
            ✓ Media uploads enabled
          </Badge>
        )}
      </CardBody>
    </Card>
  );
}
```

## Important Notes

1. **Same Integration**: OAuth 1.0a tokens are stored in the same integration's `meta_data`, not as a separate integration.

2. **Required for Media**: OAuth 1.0a is only needed if users want to upload images/media. Text-only posts work with just OAuth 2.0.

3. **Optional Step**: Users can skip OAuth 1.0a if they only want to post text tweets.

4. **Error Handling**: If OAuth 1.0a fails, the integration still works for text posts. Show a clear error message but don't block the user.

5. **Status Check**: Always check `oauth1_configured` in the integration response to determine if the button should be shown.

## Testing

1. Complete OAuth 2.0 flow (existing)
2. Check integration response - `oauth1_configured` should be `false`
3. Click "Authorize Media Uploads" button
4. Complete Twitter authorization
5. Check integration response again - `oauth1_configured` should be `true`
6. Try posting with an image - should work now

