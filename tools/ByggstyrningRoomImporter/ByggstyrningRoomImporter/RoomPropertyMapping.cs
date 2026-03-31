using System;
using System.Collections.Generic;
using System.Globalization;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;
using Byggstyrning.RoomImporter.Ifc;

namespace Byggstyrning.RoomImporter
{
    /// <summary>Maps IFC space properties onto Revit room parameters (built-in + shared names bound on the room category).</summary>
    internal static class RoomPropertyMapping
    {
        /// <summary>Revit IFC-style qualified parameter label (space after colons).</summary>
        private const string QualifiedPsetSeparator = " : ";

        /// <summary>IFC Pset_SpaceCommon property name → Revit built-in or shared param id (by name lookup).</summary>
        private static readonly IReadOnlyDictionary<string, BuiltInParameter> BuiltInByPsetName =
            new Dictionary<string, BuiltInParameter>(StringComparer.OrdinalIgnoreCase)
            {
                ["Name"] = BuiltInParameter.ROOM_NAME,
                ["LongName"] = BuiltInParameter.ROOM_NAME,
                ["Reference"] = BuiltInParameter.ROOM_NUMBER,
            };

        internal static void ApplyPsetSpaceCommon(Room room, IfcSpaceInfo sp)
        {
            foreach (var kv in sp.PsetSpaceCommon)
            {
                var key = kv.Key;
                var val = kv.Value;
                if (string.IsNullOrEmpty(val))
                    continue;

                if (BuiltInByPsetName.TryGetValue(key, out var bip))
                {
                    var p = room.get_Parameter(bip);
                    if (p != null && !p.IsReadOnly && p.StorageType == StorageType.String)
                    {
                        try
                        {
                            p.Set(val);
                        }
                        catch
                        {
                            TrySharedByName(room, key, val);
                        }
                    }
                    else
                        TrySharedByName(room, key, val);

                    continue;
                }

                TrySharedByName(room, key, val);
            }
        }

        /// <summary>
        /// Applies <see cref="IfcSpaceInfo.SpaceProperties"/>; skips <c>Pset_SpaceCommon</c> (handled by <see cref="ApplyPsetSpaceCommon"/>).
        /// Shared parameters must exist and be bound to rooms in the document.
        /// </summary>
        internal static void ApplyIfcPropertySets(Room room, IfcSpaceInfo sp)
        {
            foreach (var item in sp.SpaceProperties)
            {
                if (string.IsNullOrEmpty(item.Value))
                    continue;
                if (string.Equals(item.PsetName, "Pset_SpaceCommon", StringComparison.OrdinalIgnoreCase))
                    continue;

                if (TrySetOnRoom(room, item.PropertyName, item.Value))
                    continue;
                var qualified = item.PsetName + QualifiedPsetSeparator + item.PropertyName;
                if (TrySetOnRoom(room, qualified, item.Value))
                    continue;
                var dotted = item.PsetName + "." + item.PropertyName;
                TrySetOnRoom(room, dotted, item.Value);
            }
        }

        private static bool TrySetOnRoom(Room room, string parameterName, string value)
        {
            try
            {
                var p = room.LookupParameter(parameterName);
                return TrySetParameterValue(p, value);
            }
            catch
            {
                return false;
            }
        }

        private static bool TrySetParameterValue(Parameter? p, string val)
        {
            if (p == null || p.IsReadOnly || string.IsNullOrEmpty(val))
                return false;
            try
            {
                switch (p.StorageType)
                {
                    case StorageType.String:
                        p.Set(val);
                        return true;
                    case StorageType.Integer:
                        if (int.TryParse(val.Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var i))
                        {
                            p.Set(i);
                            return true;
                        }

                        break;
                    case StorageType.Double:
                        if (double.TryParse(val.Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out var d))
                        {
                            p.Set(d);
                            return true;
                        }

                        break;
                }
            }
            catch
            {
                /* ignore */
            }

            return false;
        }

        private static void TrySharedByName(Room room, string definitionName, string value)
        {
            try
            {
                var p = room.LookupParameter(definitionName);
                if (p == null || p.IsReadOnly)
                    return;
                if (p.StorageType == StorageType.String)
                    p.Set(value);
            }
            catch
            {
                /* ignore */
            }
        }
    }
}
