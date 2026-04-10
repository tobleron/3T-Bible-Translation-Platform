<#
.SYNOPSIS
    Prettifies a JSON file by formatting it with indentation.
.DESCRIPTION
    Takes a JSON file as input, pretty-prints it, and saves the result as <filename>_pretty.json.
.PARAMETER FileName
    The name of the JSON file to be prettified.
.EXAMPLE
    .\pretty_json.ps1 -FileName "2_NT_Matthew_004.json"
#>

param (
    [Parameter(Mandatory = $true)]
    [string]$FileName
)

try
{
    # Validate that the file exists
    if (!(Test-Path $FileName))
    {
        Write-Error "File '$FileName' not found."
        exit 1
    }

    # Check if the file has a .json extension
    if (![System.IO.Path]::GetExtension($FileName) -ieq ".json")
    {
        Write-Error "The file must have a .json extension."
        exit 1
    }

    # Generate the output file name
    $OutFile = [System.IO.Path]::Combine(
        [System.IO.Path]::GetDirectoryName($FileName),
        [System.IO.Path]::GetFileNameWithoutExtension($FileName) + "_pretty.json"
    )

    # Read, format, and save the JSON
    try
    {
        $jsonContent = Get-Content $FileName -Raw | ConvertFrom-Json
        $prettyJson = $jsonContent | ConvertTo-Json -Depth 100
        Set-Content $OutFile -Value $prettyJson -Encoding utf8
        Write-Host "Successfully created '$OutFile'"
    } catch
    {
        Write-Error "Error converting JSON: $_"
        exit 1
    }

} catch
{
    Write-Error "An unexpected error occurred: $_"
    exit 1
}
