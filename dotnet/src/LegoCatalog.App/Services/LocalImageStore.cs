using LegoCatalog.App.Configuration;

namespace LegoCatalog.App.Services;

public interface IImageStore
{
    string GetImageUrl(string fileName);

    /// <summary>
    /// Returns the image bytes, or null when the key is not canonical or absent.
    /// </summary>
    Task<ReadOnlyMemory<byte>?> ReadAsync(
        string fileName,
        CancellationToken cancellationToken);
}

/// <summary>
/// Resolves only canonical UUID image keys beneath the configured local root.
/// </summary>
public sealed class LocalImageStore : IImageStore
{
    private readonly string _rootPath;

    public LocalImageStore(CatalogRuntimeOptions options)
    {
        _rootPath = Path.GetFullPath(options.ImagesPath);
    }

    public string GetImageUrl(string fileName) => $"/images/{fileName}";

    public async Task<ReadOnlyMemory<byte>?> ReadAsync(
        string fileName,
        CancellationToken cancellationToken)
    {
        if (!TryResolvePath(fileName, out var path))
        {
            return null;
        }

        return await File.ReadAllBytesAsync(path, cancellationToken);
    }

    private bool TryResolvePath(string fileName, out string path)
    {
        path = string.Empty;
        if (!IsCanonicalImageKey(fileName))
        {
            return false;
        }

        var candidate = Path.GetFullPath(Path.Combine(_rootPath, fileName));
        var relative = Path.GetRelativePath(_rootPath, candidate);
        if (relative.StartsWith("..", StringComparison.Ordinal)
            || Path.IsPathRooted(relative)
            || !File.Exists(candidate))
        {
            return false;
        }

        path = candidate;
        return true;
    }

    public static bool IsCanonicalImageKey(string fileName)
    {
        const string suffix = ".png";
        if (!fileName.EndsWith(suffix, StringComparison.Ordinal)
            || fileName.Length != 40)
        {
            return false;
        }

        var idText = fileName[..^suffix.Length];
        return Guid.TryParseExact(idText, "D", out var id)
            && string.Equals(idText, id.ToString("D"), StringComparison.Ordinal);
    }
}
